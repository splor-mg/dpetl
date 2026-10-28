"""
Unit tests for the lfs module: settings, file selection, pointers,
endpoints, the batch API upload and the managed .gitattributes block.
"""
import pytest
import hashlib
import requests
import subprocess
from types import SimpleNamespace

from dpetl.load import github, lfs


def make_package(dpetl_load):
    return type('Package', (), {'custom': {'dpetl_load': dpetl_load}})()


def mock_response(json_data=None, ok=True):
    """A minimal stand-in for a requests.Response."""
    def raise_for_status():
        if not ok:
            raise requests.exceptions.HTTPError()
    return SimpleNamespace(
        ok=ok, status_code=200 if ok else 422, text='',
        json=lambda: json_data or {}, raise_for_status=raise_for_status,
    )


# Tests for get_lfs_settings ---------------------------------------------------
@pytest.mark.parametrize(('config', 'expected'), [
    (None, None),
    (False, None),
    (True, {'url': None, 'threshold': 50, 'patterns': []}),
    ({'threshold': 0}, {'url': None, 'threshold': 0, 'patterns': []}),
    ({'url': 'https://lfs.example/{repo}', 'patterns': 'data/*.csv.gz'},
     {'url': 'https://lfs.example/{repo}', 'threshold': 50, 'patterns': ['data/*.csv.gz']}),
])
def test_get_lfs_settings(config, expected):
    """lfs accepts true or an object, with a default threshold and no patterns."""
    assert lfs.get_lfs_settings(make_package({'lfs': config})) == expected


@pytest.mark.parametrize('config', [
    'yes',
    {'threshold': -1},
    {'threshold': '50'},
    {'threshold': True},
])
def test_get_lfs_settings_invalid(config):
    """An invalid lfs value or threshold exits instead of proceeding."""
    with pytest.raises(SystemExit):
        lfs.get_lfs_settings(make_package({'lfs': config}))


# Tests for select_paths -------------------------------------------------------
def test_select_paths_threshold():
    """Only files larger than the threshold go to LFS, never the descriptor."""
    files = {
        'data/big.csv.gz': b'x' * 2_000_001,
        'data/small.csv.gz': b'x' * 10,
        'datapackage.json': b'x' * 2_000_001,
    }

    assert lfs.select_paths(files, threshold=2, patterns=[]) == ['data/big.csv.gz']


def test_select_paths_patterns():
    """With patterns, only matching files go to LFS (* does not cross folders)."""
    files = {
        'data/a.csv.gz': b'x',
        'data/nested/b.csv.gz': b'x',
        'data-raw/c.csv.gz': b'x',
        'data/d.csv': b'x',
        'other/e.csv.gz': b'x',
    }
    patterns = ['data/*.csv.gz', 'data-raw/*.csv.gz']

    assert lfs.select_paths(files, threshold=0, patterns=patterns) == [
        'data-raw/c.csv.gz', 'data/a.csv.gz',
    ]


# Tests for pointer ------------------------------------------------------------
def test_pointer():
    """The pointer follows the Git LFS spec, with the sha256 oid and size."""
    oid = hashlib.sha256(b'data').hexdigest()

    assert lfs.pointer(b'data') == (oid, 4, (
        'version https://git-lfs.github.com/spec/v1\n'
        f'oid sha256:{oid}\n'
        'size 4\n'
    ).encode())


# Tests for get_remote_url / get_endpoint / get_auth ---------------------------
@pytest.mark.parametrize('remote', [
    'git@github.com:owner/repo.git',
    'ssh://git@github.com/owner/repo.git',
    'https://github.com/owner/repo',
    'https://user:secret@github.com/owner/repo.git',
])
def test_get_remote_url(monkeypatch, remote):
    """SSH and HTTPS remotes become an https URL without credentials or .git."""
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=remote + '\n'))

    assert lfs.get_remote_url() == 'https://github.com/owner/repo'


def test_get_remote_url_without_origin(monkeypatch):
    """A local repository without origin cannot derive the LFS endpoint."""
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=2, stdout=''))

    with pytest.raises(SystemExit):
        lfs.get_remote_url()


@pytest.mark.parametrize(('url', 'repo', 'expected'), [
    (None, 'repo', 'https://github.com/owner/repo.git/info/lfs'),
    (None, None, 'https://github.com/local-owner/local-repo.git/info/lfs'),
    ('https://lfs.example/{owner}/{repo}/', 'repo', 'https://lfs.example/owner/repo'),
    ('https://lfs.example/{owner}/{repo}', None, 'https://lfs.example/local-owner/local-repo'),
])
def test_get_endpoint(monkeypatch, url, repo, expected):
    """The endpoint is the configured server, or the repository GitHub LFS storage."""
    monkeypatch.setattr(lfs, 'get_remote_url', lambda: 'https://github.com/local-owner/local-repo')

    assert lfs.get_endpoint(url, 'owner', repo) == expected


def test_get_auth(monkeypatch):
    """GitHub uses the load token; a configured server uses LFS_USERNAME/LFS_PASSWORD."""
    monkeypatch.delenv('LFS_USERNAME', raising=False)
    monkeypatch.delenv('LFS_PASSWORD', raising=False)

    assert lfs.get_auth(None, 'token') == ('x-access-token', 'token')
    assert lfs.get_auth('https://lfs.example', 'token') is None

    monkeypatch.setenv('LFS_USERNAME', '_jwt')
    monkeypatch.setenv('LFS_PASSWORD', 'secret')

    assert lfs.get_auth('https://lfs.example', 'token') == ('_jwt', 'secret')


# Tests for upload -------------------------------------------------------------
def mock_lfs_server(monkeypatch, objects):
    """Mocks the batch API, answering with 'objects', and tracks every request."""
    calls = []

    def mock_post(url, auth=None, headers=None, json=None):
        calls.append(('POST', url, auth, json))
        return mock_response({'objects': objects} if url.endswith('/objects/batch') else {})

    def mock_put(url, data=None, auth=None, headers=None):
        calls.append(('PUT', url, auth, data))
        return mock_response()

    monkeypatch.setattr(github.session, 'post', mock_post)
    monkeypatch.setattr(github.session, 'put', mock_put)
    return calls


def test_upload(monkeypatch):
    """Objects missing on the server are uploaded and verified."""
    oid = lfs.pointer(b'data')[0]
    calls = mock_lfs_server(monkeypatch, [{
        'oid': oid, 'size': 4,
        'actions': {
            'upload': {'href': 'https://lfs.example/upload'},
            'verify': {'href': 'https://lfs.example/verify'},
        },
    }])

    lfs.upload({'data/a.csv.gz': b'data'}, 'https://lfs.example/repo', ('user', 'pass'))

    batch, put, verify = calls
    assert batch[1] == 'https://lfs.example/repo/objects/batch'
    assert batch[3]['operation'] == 'upload'
    assert batch[3]['objects'] == [{'oid': oid, 'size': 4}]
    assert put == ('PUT', 'https://lfs.example/upload', ('user', 'pass'), b'data')
    assert verify == ('POST', 'https://lfs.example/verify', ('user', 'pass'), {'oid': oid, 'size': 4})


def test_upload_skips_stored_objects(monkeypatch):
    """Objects the server already stores (no upload action) are not sent again."""
    oid = lfs.pointer(b'data')[0]
    calls = mock_lfs_server(monkeypatch, [{'oid': oid, 'size': 4}])

    lfs.upload({'data/a.csv.gz': b'data'}, 'https://lfs.example', None)

    assert [call[0] for call in calls] == ['POST']


def test_upload_presigned_url_gets_no_credentials(monkeypatch):
    """Server credentials are not sent to another host (e.g. a presigned storage URL)."""
    oid = lfs.pointer(b'data')[0]
    calls = mock_lfs_server(monkeypatch, [{
        'oid': oid, 'size': 4,
        'actions': {'upload': {'href': 'https://bucket.s3.example/obj?sig=1'}},
    }])

    lfs.upload({'data/a.csv.gz': b'data'}, 'https://lfs.example', ('user', 'pass'))

    assert calls[1] == ('PUT', 'https://bucket.s3.example/obj?sig=1', None, b'data')


def test_upload_object_error(monkeypatch, caplog):
    """An object refused by the server stops the load."""
    oid = lfs.pointer(b'data')[0]
    mock_lfs_server(monkeypatch, [{'oid': oid, 'size': 4, 'error': {'code': 422, 'message': 'too big'}}])

    with pytest.raises(SystemExit):
        lfs.upload({'data/a.csv.gz': b'data'}, 'https://lfs.example', None)

    assert 'LFS server refused data/a.csv.gz: too big' in caplog.text


def test_upload_batch_error(monkeypatch, caplog):
    """A refused batch request is logged as an LFS server error and raised."""
    monkeypatch.setattr(github.session, 'post', lambda *a, **k: mock_response({'message': 'denied'}, ok=False))

    with pytest.raises(requests.exceptions.HTTPError):
        lfs.upload({'data/a.csv.gz': b'data'}, 'https://lfs.example', None)

    assert 'LFS server error while requesting the LFS upload: 422 denied' in caplog.text


# Tests for build_gitattributes ------------------------------------------------
def test_build_gitattributes_new():
    """Without a .gitattributes, only the dpetl block is written."""
    assert lfs.build_gitattributes('', ['data/a.csv.gz']) == (
        f'{lfs.BEGIN}\n'
        'data/a.csv.gz filter=lfs diff=lfs merge=lfs -text\n'
        f'{lfs.END}\n'
    )


def test_build_gitattributes_replaces_block_keeping_user_rules():
    """The previous dpetl block is replaced and the user rules are kept."""
    current = (
        '* text=auto eol=lf\n'
        '\n'
        f'{lfs.BEGIN}\n'
        'data/old.csv.gz filter=lfs diff=lfs merge=lfs -text\n'
        f'{lfs.END}\n'
        '*.png binary\n'
    )

    assert lfs.build_gitattributes(current, ['data/new.csv.gz']) == (
        '* text=auto eol=lf\n'
        '*.png binary\n'
        '\n'
        f'{lfs.BEGIN}\n'
        'data/new.csv.gz filter=lfs diff=lfs merge=lfs -text\n'
        f'{lfs.END}\n'
    )


def test_build_gitattributes_removes_block():
    """Without LFS files, the dpetl block is removed."""
    current = f'* text=auto eol=lf\n\n{lfs.BEGIN}\ndata/old.csv.gz filter=lfs\n{lfs.END}\n'

    assert lfs.build_gitattributes(current, []) == '* text=auto eol=lf\n'
    assert lfs.build_gitattributes(f'{lfs.BEGIN}\n{lfs.END}\n', []) == ''


# Tests for store --------------------------------------------------------------
@pytest.fixture
def mock_store(monkeypatch):
    """Mocks the .gitattributes read and the upload, keeping the uploads."""
    uploads = []
    monkeypatch.setattr(lfs, 'get_gitattributes', lambda *a, **k: '* text=auto eol=lf\n')
    monkeypatch.setattr(lfs, 'upload', lambda objects, endpoint, auth: uploads.append((objects, endpoint, auth)))
    return uploads


def test_store_github(mock_store):
    """Large files are uploaded to the GitHub LFS storage and replaced by pointers."""
    files = {'data/big.csv.gz': b'big', 'data/small.csv': b'', 'datapackage.json': b'{}'}
    settings = {'url': None, 'threshold': 0, 'patterns': ['data/*.csv.gz']}

    paths = lfs.store(files, 'token', settings, owner='owner', repo='repo')

    assert paths == ['data/big.csv.gz']
    assert mock_store == [(
        {'data/big.csv.gz': b'big'},
        'https://github.com/owner/repo.git/info/lfs',
        ('x-access-token', 'token'),
    )]
    assert files['data/big.csv.gz'] == lfs.pointer(b'big')[2]
    assert files['data/small.csv'] == b''
    assert b'data/big.csv.gz filter=lfs' in files['.gitattributes']
    assert '.lfsconfig' not in files


def test_store_own_server(monkeypatch, mock_store):
    """A configured server gets the upload and is recorded in .lfsconfig."""
    monkeypatch.setenv('LFS_USERNAME', 'user')
    monkeypatch.setenv('LFS_PASSWORD', 'pass')
    files = {'data/big.csv.gz': b'big', 'datapackage.json': b'{}'}
    settings = {'url': 'https://lfs.example/{owner}/{repo}', 'threshold': 0, 'patterns': []}

    lfs.store(files, 'token', settings, owner='owner', repo='repo')

    assert mock_store[0][1:] == ('https://lfs.example/owner/repo', ('user', 'pass'))
    assert files['.lfsconfig'] == b'[lfs]\n\turl = https://lfs.example/owner/repo\n'


def test_store_without_large_files(monkeypatch):
    """Without large files nothing is uploaded and no .gitattributes is created."""
    monkeypatch.setattr(lfs, 'get_gitattributes', lambda *a, **k: '')
    monkeypatch.setattr(lfs, 'upload', lambda *a, **k: pytest.fail('nothing to upload'))
    files = {'data/small.csv': b'x', 'datapackage.json': b'{}'}

    assert lfs.store(files, 'token', {'url': None, 'threshold': 50, 'patterns': []}, owner='owner', repo='repo') == []
    assert list(files) == ['data/small.csv', 'datapackage.json']


def test_store_local_writes_config_files(monkeypatch, tmp_path, mock_store):
    """For local commits, .gitattributes and .lfsconfig are written to the working tree."""
    monkeypatch.chdir(tmp_path)
    files = {'data/big.csv.gz': b'big', 'datapackage.json': b'{}'}
    settings = {'url': 'https://lfs.example/{repo}', 'threshold': 0, 'patterns': []}
    monkeypatch.setattr(lfs, 'get_remote_url', lambda: 'https://github.com/owner/local-repo')

    lfs.store(files, 'token', settings, owner=None, repo=None)

    assert (tmp_path / '.gitattributes').read_bytes() == files['.gitattributes']
    assert (tmp_path / '.lfsconfig').read_text() == '[lfs]\n\turl = https://lfs.example/local-repo\n'


def test_get_gitattributes(monkeypatch, tmp_path):
    """The remote .gitattributes is read from GitHub, the local one from the working tree."""
    monkeypatch.setattr(github, 'get_remote_file', lambda owner, repo, token, path: b'remote\n')
    monkeypatch.chdir(tmp_path)

    assert lfs.get_gitattributes('token', 'owner', 'repo') == 'remote\n'
    assert lfs.get_gitattributes('token', None, None) == ''

    (tmp_path / '.gitattributes').write_text('local\n')

    assert lfs.get_gitattributes('token', None, None) == 'local\n'


# Tests for check_size ---------------------------------------------------------
def test_check_size(monkeypatch, caplog):
    """A file over the GitHub limit outside LFS stops the load."""
    monkeypatch.setattr(lfs, 'GITHUB_LIMIT', 1e-6)
    files = {'data/a.csv.gz': b'xx', 'data/b.csv.gz': b'xx'}

    lfs.check_size(files, ['data/a.csv.gz', 'data/b.csv.gz'])

    with pytest.raises(SystemExit):
        lfs.check_size(files, ['data/a.csv.gz'])

    assert 'rejected by GitHub: data/b.csv.gz' in caplog.text
