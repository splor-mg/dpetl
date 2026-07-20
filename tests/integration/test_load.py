"""
Integration tests for the load module: GitHub repository operations.
"""
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


# Tests for load_package -------------------------------------------------------
def test_load_package_flow(monkeypatch, tmp_path):
    """Test the full flow: validate, repo_exists, commit_remote."""
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
    monkeypatch.setattr('dpetl.load.load.github.repo_exists', fake_repo_exists)
    monkeypatch.setattr('dpetl.load.load.github.create_repo', fake_create_repo)
    monkeypatch.setattr('dpetl.load.load.github.commit_remote', fake_commit_remote)
    monkeypatch.setattr('dpetl.load.load.validate.validate_datapackage', fake_validate)

    # Create dummy file
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    (data_dir / 'file.csv').write_text('dummy')

    class FakeResource:
        path = 'data/file.csv'
        custom = {}

        def pop(self, key, default=None):
            return self.custom.pop(key, default)

    class FakePackage:
        custom = {'dpetl_load': {'owner': 'test', 'repo': 'repo'}}
        resources = [FakeResource()]
        _basepath = str(tmp_path)

        def to_json(self):
            return '{}'

    load.load_package(FakePackage())
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


def test_load_package_repo_creation(monkeypatch, tmp_path):
    """Test load_package creates repository when it doesn't exist."""
    calls = []

    def fake_repo_exists(*a):
        calls.append('repo_exists')
        return False

    def fake_create_repo(*a):
        calls.append('create_repo')

    def fake_commit_remote(*a):
        calls.append('commit_remote')

    monkeypatch.setenv('GH_TOKEN', 'fake')
    monkeypatch.setattr('dpetl.load.load.github.repo_exists', fake_repo_exists)
    monkeypatch.setattr('dpetl.load.load.github.create_repo', fake_create_repo)
    monkeypatch.setattr('dpetl.load.load.github.commit_remote', fake_commit_remote)
    monkeypatch.setattr('dpetl.load.load.validate.validate_datapackage', lambda *a: None)

    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    (data_dir / 'file.csv').write_text('dummy')

    class FakeResource:
        path = 'data/file.csv'
        custom = {}

        def pop(self, key, default=None):
            return self.custom.pop(key, default)

    class FakePackage:
        custom = {'dpetl_load': {'owner': 'test', 'repo': 'repo'}}
        resources = [FakeResource()]
        _basepath = str(tmp_path)

        def to_json(self):
            return '{}'

    load.load_package(FakePackage())
    assert calls == ['repo_exists', 'create_repo', 'commit_remote']


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

    def mock_post(url, json, headers):
        nonlocal payload
        payload = json
        return SimpleNamespace(status_code=201, raise_for_status=lambda: None)

    monkeypatch.setattr(requests, 'post', mock_post)
    github.create_repo('owner', 'repo', 'token', 'user', 'private')

    assert payload['name'] == 'repo'
    assert payload['private'] is True


# Tests for github.commit_remote -----------------------------------------------
def test_commit_remote(monkeypatch):
    """Test commit_remote creates one blob per file and commits."""
    files = {'a.txt': b'x', 'b.csv': b'y'}
    post_calls = []
    patch_called = False

    def mock_get(url, headers=None):
        data = {}
        # Distinguish URLs by exact match or specific substring
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


# Tests for github.commit_local ------------------------------------------------
@pytest.mark.parametrize(('files', 'has_changes', 'expected_commands'), [
    ({'f1.txt': b'x'}, True, 4),   # add, diff, commit, push
    ({}, False, 2),                 # add, diff only
])
def test_commit_local(monkeypatch, files, has_changes, expected_commands):
    """Test commit_local with and without changes."""
    commands = []

    def mock_run(cmd, check=False, capture_output=False):
        commands.append(cmd)
        ret = SimpleNamespace(returncode=0)
        if cmd == ['git', 'diff', '--cached', '--quiet']:
            ret.returncode = 0 if not has_changes else 1
        return ret

    monkeypatch.setattr(subprocess, 'run', mock_run)

    github.commit_local(files)

    assert len(commands) == expected_commands
    assert commands[0][0:3] == ['git', 'add', '-f']
    assert commands[1] == ['git', 'diff', '--cached', '--quiet']
    if has_changes:
        assert commands[2][0:3] == ['git', 'commit', '-m']
        assert commands[3] == ['git', 'push']
