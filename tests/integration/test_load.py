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
    def __init__(self, custom=None, basepath='/tmp', name='test_pkg'):
        self.name = name
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


def test_load_package_to_postgres(monkeypatch, dpetl_package, scoped_package):
    """With target postgres, data goes to the database and only the descriptor is committed."""
    mock_github(monkeypatch)
    committed = {}
    monkeypatch.setattr(
        'dpetl.load.load.github.commit_remote',
        lambda token, files, *a, **k: committed.update(files)
    )
    loaded = []
    table = {
        'name': 'basic',
        'path': 'postgresql://host:5432/db',
        'dialect': {'sql': {'table': 'basic', 'namespace': 'dados'}},
    }
    monkeypatch.setattr(
        'dpetl.load.load.postgres.load_tables',
        lambda package, schema: loaded.append((package.resource_names, schema)) or [table]
    )
    package = scoped_package(dpetl_package, 'basic')
    package.custom['dpetl_load'].update({'target': 'postgres', 'schema': 'dados'})

    load.load_package(package)

    assert loaded == [(['basic'], 'dados')]
    assert list(committed) == ['datapackage.json']

    descriptor = json.loads(committed['datapackage.json'])
    assert descriptor['resources'] == [table]
    assert not [key for key in descriptor if key.startswith('dpetl_')]


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


# Tests for get_target_settings ------------------------------------------------
@pytest.mark.parametrize(('dpetl_load', 'expected'), [
    ({}, {'target': 'github', 'schema': 'test_pkg'}),
    ({'target': 'github'}, {'target': 'github', 'schema': 'test_pkg'}),
    ({'target': 'postgres'}, {'target': 'postgres', 'schema': 'test_pkg'}),
    ({'target': 'postgres', 'schema': 'dados_siafi'}, {'target': 'postgres', 'schema': 'dados_siafi'}),
])
def test_get_target_settings(dpetl_load, expected):
    """target defaults to github and schema defaults to the package name."""
    package = FakePackage(custom={'dpetl_load': dpetl_load})

    assert load.get_target_settings(package) == expected


def test_get_target_settings_invalid_target(caplog):
    """An unknown target exits instead of loading somewhere unexpected."""
    package = FakePackage(custom={'dpetl_load': {'target': 'mysql'}})

    with pytest.raises(SystemExit):
        load.get_target_settings(package)

    assert 'Field "target" in "dpetl_load" must be one of: github, postgres.' in caplog.text


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
    monkeypatch.setattr(github.session, 'get', lambda *a, **k: SimpleNamespace(status_code=status_code))

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

    monkeypatch.setattr(github.session, 'post', mock_post)

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

    monkeypatch.setattr(github.session, 'post', lambda *a, **k: MockResponse())

    with pytest.raises(requests.exceptions.HTTPError):
        github.create_repo('token', 'owner', 'repo', 'user', 'private')

    assert "GitHub API error: {'message': 'Validation failed'}" in caplog.text


# Tests for github.commit_remote -----------------------------------------------
def mock_git_api(monkeypatch, tree_sha='base_tree_sha', check_tree_deletion=False, fail_on=None):
    """Mocks the GitHub git-data API sequence commit_remote walks through.
    'fail_on' makes requests to URLs containing it fail like a GitHub error."""
    patch_called = []

    def failed(url):
        return SimpleNamespace(
            ok=False, status_code=422, text='',
            json=lambda: {'message': 'GitHub refused it'},
            raise_for_status=lambda: (_ for _ in ()).throw(requests.exceptions.HTTPError(url)),
        )

    def mock_get(url, headers=None):
        if fail_on and fail_on in url:
            return failed(url)
        if url == 'https://api.github.com/repos/owner/repo':
            data = {'default_branch': 'main'}
        elif '/git/refs/heads/' in url:
            data = {'object': {'sha': 'head_sha'}}
        elif '/git/commits' in url:
            data = {'tree': {'sha': 'base_tree_sha'}}
        else:
            data = {}
        return SimpleNamespace(ok=True, status_code=200, json=lambda: data, raise_for_status=lambda: None)

    def mock_post(url, headers=None, json=None):
        if fail_on and fail_on in url:
            return failed(url)
        if '/git/trees' in url:
            if check_tree_deletion:
                assert any(item.get('sha') is None for item in json.get('tree', []))
            sha = tree_sha
        elif '/git/blobs' in url:
            sha = 'blob_sha'
        else:
            sha = 'new_commit_sha'
        return SimpleNamespace(ok=True, status_code=201, json=lambda: {'sha': sha}, raise_for_status=lambda: None)

    def mock_patch(url, headers=None, json=None):
        patch_called.append(True)
        if fail_on == 'patch':
            return failed(url)
        return SimpleNamespace(ok=True, status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr(github.session, 'get', mock_get)
    monkeypatch.setattr(github.session, 'post', mock_post)
    monkeypatch.setattr(github.session, 'patch', mock_patch)
    return patch_called


def test_commit_remote(monkeypatch):
    """commit_remote creates one blob per file and pushes a commit."""
    files = {'a.txt': b'x', 'b.csv': b'y'}
    patch_called = mock_git_api(monkeypatch, tree_sha='new_tree_sha')

    github.commit_remote('token', files, set(), owner='owner', repo='repo')

    assert patch_called == [True]


@pytest.mark.parametrize('fail_on, action', [
    ('/git/refs/heads/', 'reading branch main'),
    ('/git/blobs', 'uploading big.csv (0.0 MB)'),
    ('/git/trees', 'creating the file tree'),
    ('patch', 'updating branch main'),
])
def test_commit_remote_reports_github_errors(monkeypatch, caplog, fail_on, action):
    """A refused request stops the commit and logs GitHub's message with the failed step."""
    mock_git_api(monkeypatch, tree_sha='new_tree_sha', fail_on=fail_on)

    with pytest.raises(requests.exceptions.HTTPError):
        github.commit_remote('token', {'big.csv': b'x'}, set(), owner='owner', repo='repo')

    assert f'GitHub API error while {action}: 422 GitHub refused it' in caplog.text
    assert 'Successfully committed' not in caplog.text


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


def test_commit_remote_blob_error(monkeypatch):
    """A rejected blob upload raises HTTPError instead of failing on the missing sha."""
    mock_git_api(monkeypatch)

    def mock_post(url, headers=None, json=None):
        def raise_for_status():
            raise requests.exceptions.HTTPError()
        return SimpleNamespace(
            ok=False, status_code=403, text='',
            json=lambda: {'message': 'Forbidden'},
            raise_for_status=raise_for_status,
        )

    monkeypatch.setattr(github.session, 'post', mock_post)

    with pytest.raises(requests.exceptions.HTTPError):
        github.commit_remote('token', {'a.txt': b'x'}, set(), owner='owner', repo='repo')


def test_session_retries_rate_limit_and_server_errors():
    """The shared session retries rate limits and server errors, including POST and PATCH."""
    retry = github.session.get_adapter('https://api.github.com').max_retries

    assert retry.total == 5
    assert retry.is_retry('POST', 403)
    assert retry.is_retry('PATCH', 502)
    assert not retry.is_retry('GET', 404)


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
