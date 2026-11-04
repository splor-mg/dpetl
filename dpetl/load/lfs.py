import os
import hashlib
import logging
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from dpetl.load import github

logger = logging.getLogger(__name__)

# Files above this size (MB) go to LFS when no threshold is configured
DEFAULT_THRESHOLD = 50

# GitHub rejects files above this size (MB) outside LFS
GITHUB_LIMIT = 100

# The batch API accepts a limited number of objects per request
BATCH_SIZE = 100

LFS_MEDIA_TYPE = 'application/vnd.git-lfs+json'

BEGIN = '# BEGIN dpetl lfs (managed by dpetl, do not edit)'
END = '# END dpetl lfs'


def get_lfs_settings(package):
    """
    Extract and validate the Git LFS settings from the package custom
    metadata. Returns None when LFS is not enabled.
    """
    config = package.custom.get('dpetl_load', {}).get('lfs')

    if not config:
        return None

    if config is True:
        config = {}

    if not isinstance(config, dict):
        logger.error('Field "lfs" in "dpetl_load" must be true or an object.')
        raise SystemExit(1)

    threshold = config.get('threshold', DEFAULT_THRESHOLD)
    patterns = config.get('patterns') or []

    if isinstance(patterns, str):
        patterns = [patterns]

    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or threshold < 0:
        logger.error('Field "lfs.threshold" in "dpetl_load" must be a number of MB >= 0.')
        raise SystemExit(1)

    return {
        'url': config.get('url'),
        'threshold': threshold,
        'patterns': patterns,
    }


def select_paths(files, threshold, patterns, **kwargs):
    """
    Return the paths of the data files that go to LFS: files matching one of
    the patterns (any file, without patterns) and larger than the threshold.
    """
    return sorted(
        path for path, content in files.items()
        if path != 'datapackage.json'
        and len(content) > threshold * 1e6
        and (not patterns or any(PurePosixPath(path).full_match(p) for p in patterns))
    )


def pointer(content):
    """
    Return the sha256 oid, the size and the LFS pointer file of a content.
    """
    oid = hashlib.sha256(content).hexdigest()
    size = len(content)
    text = f'version https://git-lfs.github.com/spec/v1\noid sha256:{oid}\nsize {size}\n'

    return oid, size, text.encode()


def get_remote_url():
    """
    Return the https URL of the local repository's origin remote, without
    credentials or the .git suffix (e.g. https://github.com/owner/repo).
    """
    r = subprocess.run(
        ['git', 'remote', 'get-url', 'origin'],
        capture_output=True, text=True
    )

    if r.returncode != 0:
        logger.error('Git LFS requires an "origin" remote in the local repository.')
        raise SystemExit(1)

    url = r.stdout.strip()

    # git@github.com:owner/repo.git -> ssh://git@github.com/owner/repo.git
    if '://' not in url:
        url = 'ssh://' + url.replace(':', '/', 1)

    parts = urlsplit(url)
    path = parts.path.strip('/').removesuffix('.git')

    return f'https://{parts.hostname}/{path}'


def get_endpoint(url, owner, repo):
    """
    Return the LFS endpoint: the configured server (with {owner} and {repo}
    replaced) or the GitHub LFS storage of the repository.
    """
    if repo:
        remote = f'https://github.com/{owner}/{repo}'
    else:
        remote = get_remote_url()
        owner, repo = remote.split('/')[-2:]

    if url:
        return url.replace('{owner}', owner).replace('{repo}', repo).rstrip('/')

    return f'{remote}.git/info/lfs'


def get_auth(url, token):
    """
    Return the Basic credentials for the LFS server: LFS_USERNAME and
    LFS_PASSWORD for a configured server, the GitHub token otherwise.
    """
    if not url:
        return ('x-access-token', token)

    username = os.environ.get('LFS_USERNAME')
    password = os.environ.get('LFS_PASSWORD')

    if username or password:
        return (username or '', password or '')

    logger.debug('No LFS_USERNAME/LFS_PASSWORD set, using the LFS server anonymously.')
    return None


def check_response(r, action):
    """
    Log the LFS server error message and raise when a request failed.
    """
    return github.check_response(r, action, service='LFS server')


def transfer(endpoint, auth, href, headers):
    """
    Return the credentials for a transfer action: the server ones only when
    the action points to the same host and brings no Authorization header
    (e.g. not a presigned storage URL).
    """
    same_host = urlsplit(href).netloc == urlsplit(endpoint).netloc
    return auth if same_host and 'Authorization' not in headers else None


def upload(objects, endpoint, auth):
    """
    Upload contents to the LFS server through the batch API. Objects the
    server already stores are skipped. `objects` maps paths to contents.
    """
    headers = {'Accept': LFS_MEDIA_TYPE, 'Content-Type': LFS_MEDIA_TYPE}
    by_oid = {pointer(content)[0]: (path, content) for path, content in objects.items()}
    oids = list(by_oid)

    for start in range(0, len(oids), BATCH_SIZE):
        batch = [
            {'oid': oid, 'size': len(by_oid[oid][1])}
            for oid in oids[start:start + BATCH_SIZE]
        ]

        r = github.session.post(
            f'{endpoint}/objects/batch',
            auth=auth,
            headers=headers,
            json={
                'operation': 'upload',
                'transfers': ['basic'],
                'objects': batch,
                'hash_algo': 'sha256',
            }
        )
        check_response(r, 'requesting the LFS upload')

        for item in r.json().get('objects', []):
            path, content = by_oid[item['oid']]

            if 'error' in item:
                logger.error(
                    'LFS server refused %s: %s',
                    path, item['error'].get('message')
                )
                raise SystemExit(1)

            actions = item.get('actions') or {}

            if 'upload' not in actions:
                logger.debug('LFS server already stores %s.', path)
                continue

            action = actions['upload']
            action_headers = action.get('header', {})

            r = github.session.put(
                action['href'],
                data=content,
                auth=transfer(endpoint, auth, action['href'], action_headers),
                headers=action_headers,
            )
            check_response(r, f'uploading {path} ({len(content) / 1e6:.1f} MB)')

            if 'verify' in actions:
                action = actions['verify']
                action_headers = {**headers, **action.get('header', {})}

                r = github.session.post(
                    action['href'],
                    auth=transfer(endpoint, auth, action['href'], action_headers),
                    headers=action_headers,
                    json={'oid': item['oid'], 'size': len(content)},
                )
                check_response(r, f'verifying {path}')

            logger.info('Uploaded %s to LFS (%.1f MB).', path, len(content) / 1e6)


def get_gitattributes(token, owner, repo, **kwargs):
    """
    Return the current .gitattributes of the repository: the committed one
    on GitHub, or the working tree one for local commits.
    """
    if repo:
        content = github.get_remote_file(owner, repo, token, '.gitattributes')
        return content.decode() if content else ''

    file = Path('.gitattributes')
    return file.read_text() if file.exists() else ''


def strip_blank(lines):
    """
    Remove the trailing blank lines.
    """
    while lines and not lines[-1].strip():
        lines = lines[:-1]

    return lines


def build_gitattributes(current, paths):
    """
    Replace the dpetl block of a .gitattributes content with one LFS rule
    per path, keeping the user rules.
    """
    lines = current.splitlines()

    if BEGIN in lines and END in lines:
        before = strip_blank(lines[:lines.index(BEGIN)])
        lines = before + lines[lines.index(END) + 1:]

    lines = strip_blank(lines)

    if paths:
        if lines:
            lines.append('')
        lines += [BEGIN, *(f'{path} filter=lfs diff=lfs merge=lfs -text' for path in paths), END]

    return '\n'.join(lines) + '\n' if lines else ''


def store(files, token, lfs, owner, repo, **kwargs):
    """
    Send the large data files to LFS and replace their contents in `files`
    with LFS pointers. Adds the .gitattributes (and .lfsconfig, for a
    configured server) to the files to commit. Returns the LFS paths.
    """
    paths = select_paths(files, **lfs)

    current = get_gitattributes(token, owner, repo)
    config = {}

    # Keep the file when the block is removed, even if nothing is left
    if current or paths:
        config['.gitattributes'] = build_gitattributes(current, paths)

    if lfs['url'] or paths:
        endpoint = get_endpoint(lfs['url'], owner, repo)

    if lfs['url']:
        config['.lfsconfig'] = f'[lfs]\n\turl = {endpoint}\n'

    if paths:
        upload({path: files[path] for path in paths}, endpoint, get_auth(lfs['url'], token))

        for path in paths:
            files[path] = pointer(files[path])[2]

    for name, content in config.items():
        files[name] = content.encode()

        # Local commits stage these files from the working tree
        if not repo:
            Path(name).write_text(content)

    return paths


def check_size(files, lfs_paths):
    """
    Stop before committing when a file outside LFS exceeds the GitHub limit.
    """
    large = [
        path for path, content in files.items()
        if path not in lfs_paths and len(content) > GITHUB_LIMIT * 1e6
    ]

    if large:
        logger.error(
            'Files larger than %d MB are rejected by GitHub: %s. '
            'Enable "lfs" in "dpetl_load" (and include them in '
            '"lfs.patterns", if set) to send them to Git LFS.',
            GITHUB_LIMIT, ', '.join(large)
        )
        raise SystemExit(1)
