import pytest
import requests
import subprocess
from types import SimpleNamespace

from dpetl.load import github, load


# Helper: FakePackage ----------------------------------------------------------
class FakePackage:
    def __init__(self, custom=None, resources=None, basepath='/tmp'):
        self.custom = custom or {}
        self.resources = resources or []
        self._basepath = basepath

    def to_json(self):
        return '{}'


# Fixture para criar um pacote com um recurso dummy em um diretório temporário
@pytest.fixture
def fake_package_with_resource(tmp_path):
    """Cria um FakePackage com um recurso dummy e um arquivo CSV."""
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    (data_dir / 'file.csv').write_text('dummy')

    class FakeResource:
        path = 'data/file.csv'
        custom = {}

        def pop(self, key, default=None):
            return self.custom.pop(key, default)

    return FakePackage(
        custom={'dpetl_load': {'owner': 'test', 'repo': 'repo'}},
        resources=[FakeResource()],
        basepath=str(tmp_path)
    )


# Tests for load_package -------------------------------------------------------
def test_load_package_flow(monkeypatch, fake_package_with_resource):
    """Test the full flow: validate, repo_exists, commit_remote."""
    package = fake_package_with_resource
    calls = []

    def fake_validate(*a):
        calls.append('validate')

    def fake_repo_exists(*a):
        calls.append('repo_exists')
        return True

    def fake_create_repo(*a):
        calls.append('create_repo')

    def fake_commit_remote(*a):
        calls.append('commit_remote')

    monkeypatch.setenv('GH_TOKEN', 'fake')
    monkeypatch.setattr('dpetl.load.load._get_token', lambda *a: 'fake_token')
    monkeypatch.setattr('dpetl.load.load.github.repo_exists', fake_repo_exists)
    monkeypatch.setattr('dpetl.load.load.github.create_repo', fake_create_repo)
    monkeypatch.setattr('dpetl.load.load.github.commit_remote', fake_commit_remote)
    monkeypatch.setattr('dpetl.load.load.validate.validate_datapackage', fake_validate)

    load.load_package(package)
    assert set(calls) == {'validate', 'repo_exists', 'commit_remote'}


@pytest.mark.parametrize(('custom', 'missing_field'), [
    ({}, 'GH_TOKEN'),
    ({'dpetl_load': {'repo': 'repo'}}, 'owner'),
    ({'dpetl_load': {'owner': 'test', 'repo': 'repo', 'level': 'invalid'}}, 'level'),
    ({'dpetl_load': {'owner': 'test', 'repo': 'repo', 'visibility': 'invalid'}}, 'visibility'),
])
def test_load_package_validation_errors(monkeypatch, custom, missing_field):
    """Test load_package raises SystemExit for missing/invalid configuration."""
    if missing_field == 'GH_TOKEN':
        monkeypatch.delenv('GH_TOKEN', raising=False)
    else:
        monkeypatch.setenv('GH_TOKEN', 'fake')
    with pytest.raises(SystemExit):
        load.load_package(FakePackage(custom=custom))


def test_load_package_repo_creation(monkeypatch, fake_package_with_resource):
    """Test load_package creates repository when it doesn't exist."""
    package = fake_package_with_resource
    calls = []

    def fake_repo_exists(*a):
        calls.append('repo_exists')
        return False

    def fake_create_repo(*a):
        calls.append('create_repo')

    def fake_commit_remote(*a):
        calls.append('commit_remote')

    monkeypatch.setenv('GH_TOKEN', 'fake')
    monkeypatch.setattr('dpetl.load.load._get_token', lambda *a: 'fake_token')
    monkeypatch.setattr('dpetl.load.load.github.repo_exists', fake_repo_exists)
    monkeypatch.setattr('dpetl.load.load.github.create_repo', fake_create_repo)
    monkeypatch.setattr('dpetl.load.load.github.commit_remote', fake_commit_remote)
    monkeypatch.setattr('dpetl.load.load.validate.validate_datapackage', lambda *a: None)

    load.load_package(package)
    assert calls == ['repo_exists', 'create_repo', 'commit_remote']


def test_load_package_local_commit(monkeypatch, tmp_path):
    """Test load_package when repo is not set (local commit)."""
    calls = []

    def fake_validate(*a):
        calls.append('validate')

    def fake_commit_local(*a):
        calls.append('commit_local')

    package = FakePackage(
        custom={'dpetl_load': {'owner': 'test'}},
        basepath=str(tmp_path)
    )

    monkeypatch.setenv('GH_TOKEN', 'fake')
    monkeypatch.setattr('dpetl.load.load._get_token', lambda *a: 'fake')
    monkeypatch.setattr('dpetl.load.load.github.commit_local', fake_commit_local)
    monkeypatch.setattr('dpetl.load.load.validate.validate_datapackage', fake_validate)

    load.load_package(package)
    assert 'validate' in calls
    assert 'commit_local' in calls


# Tests for _get_token() -------------------------------------------------------
def test_get_token_github_app_priority(monkeypatch):
    """Test that GH_APP_ID + GH_APP_PRIVATE_KEY has priority over GH_TOKEN."""
    from dpetl.load.load import _get_token

    monkeypatch.setenv('GH_APP_ID', '123')
    monkeypatch.setenv('GH_APP_PRIVATE_KEY', 'key')
    monkeypatch.setenv('GH_TOKEN', 'token')

    def mock_installation(*args, **kwargs):
        return 'app_token'
    monkeypatch.setattr('dpetl.load.github.get_installation_token', mock_installation)

    token = _get_token('owner')
    assert token == 'app_token'


def test_get_token_fallback_to_gh_token(monkeypatch):
    """Test fallback to GH_TOKEN when App variables are not present."""
    from dpetl.load.load import _get_token

    monkeypatch.setenv('GH_TOKEN', 'token')
    token = _get_token('owner')
    assert token == 'token'


def test_get_token_missing_credentials(monkeypatch):
    """Test error when no credentials are available."""
    from dpetl.load.load import _get_token
    monkeypatch.delenv('GH_APP_ID', raising=False)
    monkeypatch.delenv('GH_APP_PRIVATE_KEY', raising=False)
    monkeypatch.delenv('GH_TOKEN', raising=False)

    with pytest.raises(SystemExit):
        _get_token('owner')


# Tests for github.repo_exists -------------------------------------------------
@pytest.mark.parametrize(('status_code', 'expected'), [
    (200, True),
    (404, False),
])
def test_repo_exists(monkeypatch, status_code, expected):
    """Test repo_exists with different HTTP status codes."""
    def mock_get(*args, **kwargs):
        return SimpleNamespace(status_code=status_code)
    monkeypatch.setattr(requests, 'get', mock_get)
    assert github.repo_exists('owner', 'repo', 'token') is expected


# Tests for github.create_repo -------------------------------------------------
def test_create_repo(monkeypatch):
    """Test create_repo sends correct payload."""
    payload = None

    class MockResponse:
        def __init__(self):
            self.status_code = 201
            self.ok = True

        def raise_for_status(self):
            pass

        def json(self):
            return {}

    def mock_post(url, json, headers):
        nonlocal payload
        payload = json
        return MockResponse()

    monkeypatch.setattr(requests, 'post', mock_post)

    github.create_repo('owner', 'repo', 'token', 'user', 'private')

    assert payload['name'] == 'repo'
    assert payload['private'] is True


def test_create_repo_api_error(monkeypatch, caplog):
    """Test that API error is logged when create_repo fails."""
    class MockResponse:
        def __init__(self):
            self.status_code = 422
            self.ok = False

        def json(self):
            return {'message': 'Validation failed'}

        def raise_for_status(self):
            raise requests.exceptions.HTTPError()

    def mock_post(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr(requests, 'post', mock_post)

    with pytest.raises(requests.exceptions.HTTPError):
        github.create_repo('owner', 'repo', 'token', 'user', 'private')

    assert "GitHub API error: {'message': 'Validation failed'}" in caplog.text


# Tests for github.commit_remote -----------------------------------------------
def test_commit_remote(monkeypatch):
    """Test commit_remote creates one blob per file and commits."""
    files = {'a.txt': b'x', 'b.csv': b'y'}
    post_calls = []
    patch_called = False

    def mock_get(url, headers=None):
        data = {}
        if url == 'https://api.github.com/repos/owner/repo':
            data = {'default_branch': 'main'}
        elif '/git/refs/heads/' in url:
            data = {'object': {'sha': 'head_sha'}}
        elif '/git/commits' in url:
            data = {'tree': {'sha': 'base_tree_sha'}}
        return SimpleNamespace(status_code=200, json=lambda: data, raise_for_status=lambda: None)

    def mock_post(url, headers=None, json=None):
        nonlocal post_calls
        post_calls.append(url)
        sha = 'blob_sha' if 'blobs' in url else 'new_tree_sha' if 'trees' in url else 'new_commit_sha'
        return SimpleNamespace(status_code=201, json=lambda: {'sha': sha}, raise_for_status=lambda: None)

    def mock_patch(url, headers=None, json=None):
        nonlocal patch_called
        patch_called = True
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(requests, 'get', mock_get)
    monkeypatch.setattr(requests, 'post', mock_post)
    monkeypatch.setattr(requests, 'patch', mock_patch)

    github.commit_remote('owner', 'repo', 'token', files)

    blob_posts = [u for u in post_calls if 'blobs' in u]
    assert len(blob_posts) == len(files)
    assert patch_called is True


def test_commit_remote_no_changes(monkeypatch):
    """Test commit_remote when there are no changes (tree unchanged)."""
    files = {'a.txt': b'x'}

    def mock_get(url, headers=None):
        data = {}
        if url == 'https://api.github.com/repos/owner/repo':
            data = {'default_branch': 'main'}
        elif '/git/refs/heads/' in url:
            data = {'object': {'sha': 'head_sha'}}
        elif '/git/commits' in url:
            data = {'tree': {'sha': 'base_tree_sha'}}
        return SimpleNamespace(status_code=200, json=lambda: data, raise_for_status=lambda: None)

    def mock_post(url, headers=None, json=None):
        if '/git/trees' in url:
            return SimpleNamespace(status_code=201, json=lambda: {'sha': 'base_tree_sha'}, raise_for_status=lambda: None)
        elif '/git/blobs' in url:
            return SimpleNamespace(status_code=201, json=lambda: {'sha': 'blob_sha'}, raise_for_status=lambda: None)
        else:
            return SimpleNamespace(status_code=201, json=lambda: {'sha': 'new_commit_sha'}, raise_for_status=lambda: None)

    def mock_patch(url, headers=None, json=None):
        assert False, "patch should not be called"

    monkeypatch.setattr(requests, 'get', mock_get)
    monkeypatch.setattr(requests, 'post', mock_post)
    monkeypatch.setattr(requests, 'patch', mock_patch)

    github.commit_remote('owner', 'repo', 'token', files)


# Tests for github.commit_local ------------------------------------------------
@pytest.mark.parametrize(('files', 'has_changes', 'expected_commands'), [
    ({'f1.txt': b'x'}, True, 4),
    ({}, False, 2),
])
def test_commit_local(monkeypatch, files, has_changes, expected_commands):
    """Test commit_local with and without changes."""
    commands = []

    def mock_run(cmd, check=False, capture_output=False, **kwargs):
        commands.append(cmd)
        ret = SimpleNamespace(returncode=0)
        if cmd == ['git', 'diff', '--cached', '--quiet']:
            ret.returncode = 0 if not has_changes else 1
        return ret

    def mock_check_output(cmd, **kwargs):
        if cmd == ['git', 'rev-parse', '--short', 'HEAD']:
            return 'abc1234\n'
        return b''

    monkeypatch.setattr(subprocess, 'run', mock_run)
    monkeypatch.setattr(subprocess, 'check_output', mock_check_output)

    github.commit_local(files)

    assert len(commands) == expected_commands
    assert commands[0][0:3] == ['git', 'add', '-f']
    assert commands[1] == ['git', 'diff', '--cached', '--quiet']
    if has_changes:
        assert commands[2][0:3] == ['git', 'commit', '-m']
        assert commands[3] == ['git', 'push']
