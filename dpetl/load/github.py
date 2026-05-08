import base64
import requests
from datetime import datetime

GITHUB_API = 'https://api.github.com'


def repo_exists(owner, repo, token):
    """
    Check if a GitHub repository exists for a given owner.
    """

    url = f'{GITHUB_API}/repos/{owner}/{repo}'
    r = requests.get(url, headers={'Authorization': f'token {token}'})
    return r.status_code == 200


def create_repo(owner, repo, token, private=False, org=False):
    """
    Create a new GitHub repository under a user or organization.
    """

    # Select correct endpoint: user or organization
    if org:
        url = f'{GITHUB_API}/orgs/{owner}/repos'
    else:
        url = f'{GITHUB_API}/user/repos'

    # Repository configuration
    payload = {
        'name': repo,
        'private': private,
        'auto_init': True
    }

    r = requests.post(
        url,
        json=payload,
        headers={'Authorization': f'token {token}'}
    )

    r.raise_for_status()


def commit_files(owner, repo, token, files):
    """
    Create a single commit with multiple files using the GitHub Git Data API.
    """

    # Base repository API URL and headers
    url = f'{GITHUB_API}/repos/{owner}/{repo}'

    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github+json'
    }

    # Retrieve current HEAD commit and tree
    r = requests.get(f'{url}/git/refs/heads/main', headers=headers)
    r.raise_for_status()

    sha = r.json()['object']['sha']

    commit = requests.get(f'{url}/git/commits/{sha}', headers=headers).json()

    base_tree = commit['tree']['sha']

    # Create blobs for each file
    items = []
    for path, content in files.items():
        blob = requests.post(
            f'{url}/git/blobs',
            headers=headers,
            json={
                'content': base64.b64encode(content).decode(),
                'encoding': 'base64'
            }
        ).json()

        items.append({
            'path': path,
            'mode': '100644',
            'type': 'blob',
            'sha': blob['sha']
        })

    # Build updated file tree
    tree = requests.post(
        f'{url}/git/trees',
        headers=headers,
        json={
            'base_tree': base_tree,
            'tree': items
        }
    ).json()

    # Create commit with timestamp
    timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    new_commit = requests.post(
        f'{url}/git/commits',
        headers=headers,
        json={
            'message': f'update data package at: {timestamp}',
            'tree': tree['sha'],
            'parents': [sha]
        }
    ).json()

    # Update branch to new commit
    requests.patch(
        f'{url}/git/refs/heads/main',
        headers=headers,
        json={'sha': new_commit['sha']}
    )
