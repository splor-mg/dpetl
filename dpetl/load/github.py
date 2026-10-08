import base64
import json
import logging
import requests
import subprocess
import time
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Retry rate limits and temporary server errors in every request
session = requests.Session()
session.mount('https://', HTTPAdapter(max_retries=Retry(
    total=5,
    backoff_factor=2,
    status_forcelist=(403, 429, 500, 502, 503, 504),
    allowed_methods=None,
    raise_on_status=False
)))


def get_repo_settings(package):
    """
    Extract and validate repository settings from the package custom metadata.
    """
    dpetl = package.custom.get('dpetl_load', {})
    owner = dpetl.get('owner')
    repo = dpetl.get('repo')
    level = dpetl.get('level') or 'user'
    visibility = dpetl.get('visibility') or 'private'

    if repo and not owner:
        logger.error('Missing required field "owner" in "dpetl_load".')
        raise SystemExit(1)

    if level not in ('user', 'orgs'):
        logger.error('Field "level" in "dpetl_load" must be "user" or "orgs".')
        raise SystemExit(1)

    if visibility not in ('public', 'private'):
        logger.error('Field "visibility" in "dpetl_load" must be "public" or "private".')
        raise SystemExit(1)

    return {
        'owner': owner,
        'repo': repo,
        'level': level,
        'visibility': visibility,
    }


def get_installation_token(app_id, private_key, owner, installation_id=None):
    """
    Generate a temporary Installation Access Token using GitHub App credentials.
    """
    try:
        import jwt
    except ImportError:
        raise ImportError(
            'GitHub App authentication requires additional dependencies. '
            'Install them with: poetry install --extras github-app'
        )

    # Generate a JWT signed with the private key
    now = int(time.time())
    payload = {
        'iat': now - 60,
        'exp': now + 540,
        'iss': str(app_id),
    }
    app_jwt = jwt.encode(payload, private_key, algorithm='RS256')

    jwt_headers = {
        'Authorization': f'Bearer {app_jwt}',
        'Accept': 'application/vnd.github+json',
    }

    # Discover the installation_id if it was not provided
    if not installation_id:
        r = session.get(
            f'https://api.github.com/orgs/{owner}/installation',
            headers=jwt_headers
        )
        r.raise_for_status()

        installation_id = r.json()['id']
        logger.debug(f'Installation ID automatically discovered: {installation_id}')

    # Request the Installation Access Token
    r = session.post(
        f'https://api.github.com/app/installations/{installation_id}/access_tokens',
        headers=jwt_headers,
    )
    r.raise_for_status()

    return r.json()['token']


def repo_exists(token, owner, repo, **kwargs):
    """
    Check if a GitHub repository exists for a given owner.
    """
    url = f'https://api.github.com/repos/{owner}/{repo}'
    r = session.get(url, headers={'Authorization': f'Bearer {token}'})
    return r.status_code == 200


def create_repo(token, owner, repo, level, visibility, **kwargs):
    """
    Create a new GitHub repository under a user or organization.
    """
    logger.info(f'Creating repository {repo}.')

    # Select correct endpoint: user or organization
    if level == 'orgs':
        url = f'https://api.github.com/orgs/{owner}/repos'
    else:
        url = f'https://api.github.com/user/repos'

    # Repository configuration
    payload = {
        'name': repo,
        'private': visibility == 'private',
        'auto_init': True
    }

    r = session.post(
        url,
        json=payload,
        headers={'Authorization': f'Bearer {token}'}
    )

    if not r.ok:
        logger.error('GitHub API error: %s', r.json())

    r.raise_for_status()


def get_remote_descriptor(owner, repo, token):
    """
    Retrieve the datapackage.json currently committed to a GitHub repository.
    Returns None if the repository has no descriptor yet.
    """
    url = f'https://api.github.com/repos/{owner}/{repo}/contents/datapackage.json'
    r = session.get(url, headers={'Authorization': f'Bearer {token}'})

    if r.status_code == 404:
        return None

    r.raise_for_status()
    return base64.b64decode(r.json()['content'])


def get_deletions(token, files, owner, repo, **kwargs):
    """
    Compare the previously committed datapackage.json against the current
    resource paths and return paths that no longer belong to the data
    package (removed, merged or renamed resources).
    """
    descriptor = get_remote_descriptor(owner, repo, token) if repo else get_local_descriptor()

    if not descriptor:
        return set()

    # Only repository files can be deleted (not e.g. postgresql:// tables)
    previous_paths = {
        resource['path'] for resource in json.loads(descriptor).get('resources', [])
        if isinstance(resource.get('path'), str) and '://' not in resource['path']
    }

    current_paths = files.keys() - {'datapackage.json'}
    return previous_paths - current_paths


def check_response(r, action):
    """
    Log the GitHub error message and raise when a request failed.
    """
    if r.ok:
        return r

    try:
        message = r.json().get('message')
    except ValueError:
        message = r.text

    logger.error(
        'GitHub API error while %s: %s %s',
        action, r.status_code, message
    )
    r.raise_for_status()


def commit_remote(token, files, deletions, owner, repo, **kwargs):
    """
    Create a single commit with multiple files using the GitHub Git Data API.
    Paths listed in `deletions` are removed from the tree.
    """
    # Base repository API URL and headers
    url = f'https://api.github.com/repos/{owner}/{repo}'

    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json'
    }

    # Get repository information

    r = session.get(url, headers=headers)
    check_response(r, f'reading repository {owner}/{repo}')
    branch = r.json()['default_branch']

    # Retrieve current HEAD commit and tree
    r = session.get(f'{url}/git/refs/heads/{branch}', headers=headers)
    check_response(r, f'reading branch {branch}')
    sha = r.json()['object']['sha']

    r = requests.get(f'{url}/git/commits/{sha}', headers=headers)
    check_response(r, f'reading commit {sha}')

    base_tree = r.json()['tree']['sha']

    # Create blobs for each file
    items = []
    for path, content in files.items():
        r = session.post(
            f'{url}/git/blobs',
            headers=headers,
            json={
                'content': base64.b64encode(content).decode(),
                'encoding': 'base64'
            }
        )
        check_response(r, f'uploading {path} ({len(content) / 1e6:.1f} MB)')

        items.append({
            'path': path,
            'mode': '100644',
            'type': 'blob',
            'sha': r.json()['sha']
        })

    # Remove resources that no longer belong to the data package
    if deletions:
        logger.debug('Removing outdated resources: %s', ', '.join(deletions))

        for path in deletions:
            items.append({
                'path': path,
                'mode': '100644',
                'type': 'blob',
                'sha': None
            })

    # Build updated file tree
    r = session.post(
        f'{url}/git/trees',
        headers=headers,
        json={
            'base_tree': base_tree,
            'tree': items
        }
    )
    check_response(r, 'creating the file tree')
    tree = r.json()

    if tree['sha'] == base_tree:
        logger.info('No changes to commit.')
        return

    # Create commit with timestamp
    timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    r = session.post(
        f'{url}/git/commits',
        headers=headers,
        json={
            'message': f'update data package at: {timestamp}',
            'tree': tree['sha'],
            'parents': [sha]
        }
    )
    check_response(r, 'creating the commit')
    new_commit = r.json()

    # Update branch to new commit
    r = requests.patch(
        f'{url}/git/refs/heads/{branch}',
        headers=headers,
        json={'sha': new_commit['sha']}
    )
    check_response(r, f'updating branch {branch}')

    logger.info(
        'Successfully committed %d files to %s/%s. Commit=%s Files=[%s]',
        len(files),
        owner,
        repo,
        new_commit['sha'][:7],
        ', '.join(files.keys())
    )


def get_local_descriptor():
    """
    Retrieve the datapackage.json currently committed in the local repository.
    Returns None if there is no previous commit or descriptor.
    """
    r = subprocess.run(
        ['git', 'show', 'HEAD:datapackage.json'],
        capture_output=True
    )
    return r.stdout if r.returncode == 0 else None


def commit_local(files, deletions=()):
    """
    Commit and push local repository changes.
    Paths listed in `deletions` are removed from the repository.
    """
    if deletions:
        logger.debug('Removing outdated resources: %s', ', '.join(deletions))
        subprocess.run(['git', 'rm', '-f', '--ignore-unmatch', *deletions], check=True)

    subprocess.run(['git', 'add', '-f', *files.keys()], check=True)

    changes = subprocess.run(['git', 'diff', '--cached', '--quiet'])
    if changes.returncode == 0:
        logger.info('No changes to commit.')
        return

    timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    subprocess.run(['git', 'commit', '-m', f'update data package at: {timestamp}'], check=True)

    subprocess.run(['git', 'push'], check=True)

    commit_sha = subprocess.check_output(
        ['git', 'rev-parse', '--short', 'HEAD'],
        text=True
    ).strip()

    logger.info(
        'Successfully committed and pushed changes. Commit=%s Files=[%s]',
        commit_sha,
        ', '.join(files.keys())
    )
