"""
Integration tests for the load module:
GitHub repository operations, authentication, and commit handling.
"""
import json
import pytest
import requests
import subprocess
from types import SimpleNamespace

from dpetl.load import github, load


class FakePackage:
    """A minimal stand-in for cases that need a custom config the shared
    dpetl_package fixture doesn't represent (missing/invalid dpetl_load)."""
    def __init__(self, custom=None, basepath='/tmp'):
        self.custom = custom or {}
        self.resources = []
        self._basepath = basepath

    def to_json(self):
        return '{}'


def mock_github(monkeypatch, repo_exists=True, deletions=None):
    """Mocks every github.* boundary call load_package makes, tracking which ran."""
    calls = []
    monkeypatch.setenv('GH_TOKEN', 'fake')
    monkeypatch.setattr('dpetl.load.load._get_token', lambda *a: 'fake_token')
    monkeypatch.setattr('dpetl.load.load.validate.validate_datapackage', lambda *a, **k: calls.append('validate'))
    monkeypatch.setattr('dpetl.load.load.github.repo_exists', lambda *a, **k: calls.append('repo_exists') or repo_exists)
    monkeypatch.setattr('dpetl.load.load.github.create_repo', lambda *a, **k: calls.append('create_repo'))
    monkeypatch.setattr('dpetl.load.load.github.get_deletions', lambda *a, **k: calls.append('get_deletions') or (deletions or set()))
    monkeypatch.setattr('dpetl.load.load.github.commit_remote', lambda *a, **k: calls.append('commit_remote'))
    monkeypatch.setattr('dpetl.load.load.github.commit_local', lambda *a, **k: calls.append('commit_local'))
    return calls


# Tests for load_package -------------------------------------------------------
def test_load_package_flow(monkeypatch, dpetl_package, scoped_package):
    """The full flow: validate, repo_exists, get_deletions, commit_remote."""
    calls = mock_github(monkeypatch, repo_exists=True)
    package = scoped_package(dpetl_package, 'basic')

    load.load_package(package)

    assert set(calls) == {'validate', 'repo_exists', 'get_deletions', 'commit_remote'}


def test_load_package_repo_creation(monkeypatch, dpetl_package, scoped_package):
    """When the repo doesn't exist yet, it's created before committing."""
    calls = mock_github(monkeypatch, repo_exists=False)
    package = scoped_package(dpetl_package, 'basic')

    load.load_package(package)

    assert calls == ['repo_exists', 'create_repo', 'validate', 'get_deletions', 'commit_remote']


def test_load_package_strips_dpetl_properties(monkeypatch, dpetl_package, scoped_package):
    """dpetl_* settings (including dpetl_linktable) are not published in datapackage.json."""
    mock_github(monkeypatch)
    committed = {}
    monkeypatch.setattr(
        'dpetl.load.load.github.commit_remote',
        lambda token, files, *a, **k: committed.update(files)
    )
    package = scoped_package(dpetl_package, 'basic')
    package.custom['dpetl_linktable'] = {'resource_list': ['basic']}

    load.load_package(package)

    descriptor = json.loads(committed['datapackage.json'])
    assert not [key for key in descriptor if key.startswith('dpetl_')]
    assert not [
        key for resource in descriptor['resources']
        for key in resource if key.startswith('dpetl_')
    ]


def test_load_package_local_commit(monkeypatch, tmp_path):
    """When 'repo' isn't set, files are committed locally instead of to GitHub."""
    calls = mock_github(monkeypatch)
    package = FakePackage(custom={'dpetl_load': {'owner': 'test'}}, basepath=str(tmp_path))

    load.load_package(package)

    assert 'validate' in calls
    assert 'commit_local' in calls


@pytest.mark.parametrize(('custom', 'missing_field'), [
    ({}, 'GH_TOKEN'),
    ({'dpetl_load': {'repo': 'repo'}}, 'owner'),
    ({'dpetl_load': {'owner': 'test', 'repo': 'repo', 'level': 'invalid'}}, 'level'),
    ({'dpetl_load': {'owner': 'test', 'repo': 'repo', 'visibility': 'invalid'}}, 'visibility'),
])
def test_load_package_validation_errors(monkeypatch, custom, missing_field):
    """Missing/invalid dpetl_load configuration exits instead of proceeding."""
    if missing_field == 'GH_TOKEN':
        monkeypatch.delenv('GH_TOKEN', raising=False)
    else:
        monkeypatch.setenv('GH_TOKEN', 'fake')

    with pytest.raises(SystemExit):
        load.load_package(FakePackage(custom=custom))


# Tests for _get_token ---------------------------------------------------------
def test_get_token_github_app_priority(monkeypatch):
    """GH_APP_ID + GH_APP_PRIVATE_KEY takes priority over GH_TOKEN."""
    from dpetl.load.load import _get_token

    monkeypatch.setenv('GH_APP_ID', '123')
    monkeypatch.setenv('GH_APP_PRIVATE_KEY', 'key')
    monkeypatch.setenv('GH_TOKEN', 'token')
    monkeypatch.setattr('dpetl.load.github.get_installation_token', lambda *a, **k: 'app_token')

    assert _get_token('owner') == 'app_token'


def test_get_token_fallback_to_gh_token(monkeypatch):
    """Falls back to GH_TOKEN when App variables aren't present."""
    from dpetl.load.load import _get_token

    monkeypatch.setenv('GH_TOKEN', 'token')

    assert _get_token('owner') == 'token'


def test_get_token_missing_credentials(monkeypatch):
    """No credentials at all exits instead of proceeding unauthenticated."""
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
    """repo_exists reflects the HTTP status code."""
    monkeypatch.setattr(requests, 'get', lambda *a, **k: SimpleNamespace(status_code=status_code))

    assert github.repo_exists('token', 'owner', 'repo') is expected


# Tests for github.create_repo -------------------------------------------------
@pytest.mark.parametrize('level, expected_url', [
    ('user', 'https://api.github.com/user/repos'),
    ('orgs', 'https://api.github.com/orgs/owner/repos'),
])
def test_create_repo(monkeypatch, level, expected_url):
    """create_repo sends the right payload to the right endpoint for each level."""
    captured = {}

    class MockResponse:
        status_code = 201
        ok = True

        def raise_for_status(self):
            pass

        def json(self):
            return {}

    def mock_post(url, json, headers):
        captured['url'] = url
        captured['payload'] = json
        return MockResponse()

    monkeypatch.setattr(requests, 'post', mock_post)

    github.create_repo('token', 'owner', 'repo', level, 'private')

    assert captured['url'] == expected_url
    assert captured['payload']['name'] == 'repo'
    assert captured['payload']['private'] is True


def test_create_repo_api_error(monkeypatch, caplog):
    """An API error is logged and re-raised, not swallowed."""
    class MockResponse:
        status_code = 422
        ok = False

        def json(self):
            return {'message': 'Validation failed'}

        def raise_for_status(self):
            raise requests.exceptions.HTTPError()

    monkeypatch.setattr(requests, 'post', lambda *a, **k: MockResponse())

    with pytest.raises(requests.exceptions.HTTPError):
        github.create_repo('token', 'owner', 'repo', 'user', 'private')

    assert "GitHub API error: {'message': 'Validation failed'}" in caplog.text


# Tests for github.commit_remote -----------------------------------------------
def mock_git_api(monkeypatch, tree_sha='base_tree_sha', check_tree_deletion=False):
    """Mocks the GitHub git-data API sequence commit_remote walks through."""
    patch_called = []

    def mock_get(url, headers=None):
        if url == 'https://api.github.com/repos/owner/repo':
            data = {'default_branch': 'main'}
        elif '/git/refs/heads/' in url:
            data = {'object': {'sha': 'head_sha'}}
        elif '/git/commits' in url:
            data = {'tree': {'sha': 'base_tree_sha'}}
        else:
            data = {}
        return SimpleNamespace(status_code=200, json=lambda: data, raise_for_status=lambda: None)

    def mock_post(url, headers=None, json=None):
        if '/git/trees' in url:
            if check_tree_deletion:
                assert any(item.get('sha') is None for item in json.get('tree', []))
            sha = tree_sha
        elif '/git/blobs' in url:
            sha = 'blob_sha'
        else:
            sha = 'new_commit_sha'
        return SimpleNamespace(status_code=201, json=lambda: {'sha': sha}, raise_for_status=lambda: None)

    def mock_patch(url, headers=None, json=None):
        patch_called.append(True)
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(requests, 'get', mock_get)
    monkeypatch.setattr(requests, 'post', mock_post)
    monkeypatch.setattr(requests, 'patch', mock_patch)
    return patch_called


def test_commit_remote(monkeypatch):
    """commit_remote creates one blob per file and pushes a commit."""
    files = {'a.txt': b'x', 'b.csv': b'y'}
    patch_called = mock_git_api(monkeypatch, tree_sha='new_tree_sha')

    github.commit_remote('token', files, set(), owner='owner', repo='repo')

    assert patch_called == [True]


def test_commit_remote_with_deletions(monkeypatch):
    """Deleted files show up in the new tree with sha=None."""
    files = {'new_file.csv': b'x'}
    patch_called = mock_git_api(monkeypatch, tree_sha='new_tree_sha', check_tree_deletion=True)

    github.commit_remote('token', files, {'old_file.csv'}, owner='owner', repo='repo')

    assert patch_called == [True]


def test_commit_remote_no_changes(monkeypatch):
    """When the new tree matches the base tree, no commit is pushed."""
    files = {'a.txt': b'x'}
    patch_called = mock_git_api(monkeypatch, tree_sha='base_tree_sha')

    github.commit_remote('token', files, set(), owner='owner', repo='repo')

    assert patch_called == []


# Tests for github.commit_local ------------------------------------------------
@pytest.mark.parametrize(('files', 'has_changes', 'expected_commands'), [
    ({'f1.txt': b'x'}, True, 4),
    ({}, False, 2),
])
def test_commit_local(monkeypatch, files, has_changes, expected_commands):
    """commit_local stages, diffs, and only commits+pushes when there are changes."""
    commands = []

    def mock_run(cmd, check=False, capture_output=False, **kwargs):
        commands.append(cmd)
        returncode = 0
        if cmd == ['git', 'diff', '--cached', '--quiet']:
            returncode = 1 if has_changes else 0
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(subprocess, 'run', mock_run)
    monkeypatch.setattr(subprocess, 'check_output', lambda cmd, **k: 'abc1234\n')

    github.commit_local(files)

    assert len(commands) == expected_commands
    assert commands[0][0:3] == ['git', 'add', '-f']
    assert commands[1] == ['git', 'diff', '--cached', '--quiet']
    if has_changes:
        assert commands[2][0:3] == ['git', 'commit', '-m']
        assert commands[3] == ['git', 'push']


def test_commit_local_with_deletions(monkeypatch):
    """Deleted resources are removed from git before the new files are staged."""
    commands = []

    def mock_run(cmd, check=False, capture_output=False, **kwargs):
        commands.append(cmd)
        returncode = 1 if cmd == ['git', 'diff', '--cached', '--quiet'] else 0
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(subprocess, 'run', mock_run)
    monkeypatch.setattr(subprocess, 'check_output', lambda cmd, **k: 'abc1234\n')

    github.commit_local({'new_file.csv': b'x'}, {'old_file.csv'})

    assert ['git', 'rm', '-f', '--ignore-unmatch', 'old_file.csv'] in commands
    assert ['git', 'add', '-f', 'new_file.csv'] in commands
    assert any(cmd[0:3] == ['git', 'commit', '-m'] for cmd in commands)
    assert ['git', 'push'] in commands
