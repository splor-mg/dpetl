"""
Unit tests for the github module: installation tokens,
repository settings, descriptor retrieval, and deletion detection.
"""
import pytest
import base64
import requests
import subprocess
from types import SimpleNamespace

from dpetl.load import github


def mock_response(status_code, json_data=None, raises=False):
    """A minimal stand-in for a requests.Response."""
    def raise_for_status():
        if raises:
            raise requests.exceptions.HTTPError()
    return SimpleNamespace(status_code=status_code, json=lambda: json_data, raise_for_status=raise_for_status)


# Tests for get_installation_token ---------------------------------------------
def test_get_installation_token_missing_dependencies(monkeypatch):
    """ImportError is raised if PyJWT is not installed."""
    monkeypatch.setitem(__import__('sys').modules, 'jwt', None)

    with pytest.raises(ImportError, match='GitHub App authentication requires additional dependencies'):
        github.get_installation_token('123', 'key', 'owner')


def test_get_installation_token_with_installation_id(monkeypatch):
    """Success when installation_id is provided directly."""
    import jwt
    monkeypatch.setattr(jwt, 'encode', lambda *a, **k: 'fake_jwt')
    monkeypatch.setattr(requests, 'post', lambda url, headers: mock_response(201, {'token': 'fake_install_token'}))

    token = github.get_installation_token('123', 'key', 'owner', '456')

    assert token == 'fake_install_token'


def test_get_installation_token_auto_discovery(monkeypatch):
    """Without installation_id, it's discovered via GET before requesting the token."""
    import jwt
    monkeypatch.setattr(jwt, 'encode', lambda *a, **k: 'fake_jwt')

    calls = []
    monkeypatch.setattr(requests, 'get', lambda url, headers: calls.append(('GET', url)) or mock_response(200, {'id': 789}))
    monkeypatch.setattr(requests, 'post', lambda url, headers: calls.append(('POST', url)) or mock_response(201, {'token': 'fake_token'}))

    github.get_installation_token('123', 'key', 'owner')

    assert ('GET', 'https://api.github.com/orgs/owner/installation') in calls
    assert ('POST', 'https://api.github.com/app/installations/789/access_tokens') in calls


def test_get_installation_token_request_failure(monkeypatch):
    """An HTTP error during discovery propagates instead of being swallowed."""
    import jwt
    monkeypatch.setattr(jwt, 'encode', lambda *a, **k: 'fake_jwt')
    monkeypatch.setattr(requests, 'get', lambda *a, **k: mock_response(404, raises=True))

    with pytest.raises(requests.exceptions.HTTPError):
        github.get_installation_token('123', 'key', 'owner')


# Tests for get_repo_settings --------------------------------------------------
def make_package(dpetl_load):
    return type('Package', (), {'custom': {'dpetl_load': dpetl_load}})()


def test_get_repo_settings_valid():
    """A fully valid dpetl_load config is returned as-is."""
    package = make_package({'owner': 'test', 'repo': 'repo', 'level': 'orgs', 'visibility': 'public'})

    settings = github.get_repo_settings(package)

    assert settings == {'owner': 'test', 'repo': 'repo', 'level': 'orgs', 'visibility': 'public'}


@pytest.mark.parametrize('dpetl_load', [
    {'repo': 'repo'},   # missing owner
    {'owner': 'test', 'repo': 'repo', 'level': 'invalid'},
    {'owner': 'test', 'repo': 'repo', 'visibility': 'invalid'},
])
def test_get_repo_settings_invalid(dpetl_load):
    """Missing owner, or an invalid level/visibility, exits instead of proceeding."""
    with pytest.raises(SystemExit):
        github.get_repo_settings(make_package(dpetl_load))


# Tests for get_remote_descriptor / get_local_descriptor -----------------------
def test_get_remote_descriptor_not_found(monkeypatch):
    """A 404 means no descriptor exists yet, returned as None."""
    monkeypatch.setattr(requests, 'get', lambda url, headers: mock_response(404))

    assert github.get_remote_descriptor('owner', 'repo', 'token') is None


def test_get_remote_descriptor_success(monkeypatch):
    """The base64-encoded content from the GitHub API is decoded."""
    content = base64.b64encode(b'{"resources": []}').decode()
    monkeypatch.setattr(requests, 'get', lambda url, headers: mock_response(200, {'content': content}))

    assert github.get_remote_descriptor('owner', 'repo', 'token') == b'{"resources": []}'


def test_get_local_descriptor_success(monkeypatch):
    """A successful 'git show' returns its stdout."""
    monkeypatch.setattr(subprocess, 'run', lambda cmd, capture_output=True:
                         SimpleNamespace(returncode=0, stdout=b'{"resources": []}'))

    assert github.get_local_descriptor() == b'{"resources": []}'


def test_get_local_descriptor_not_found(monkeypatch):
    """A failed 'git show' (e.g. no prior commit) returns None."""
    monkeypatch.setattr(subprocess, 'run', lambda cmd, capture_output=True:
                         SimpleNamespace(returncode=128, stdout=b''))

    assert github.get_local_descriptor() is None


# Tests for get_deletions ------------------------------------------------------
@pytest.mark.parametrize('mocked_function, kwargs', [
    ('get_remote_descriptor', {'owner': 'owner', 'repo': 'repo'}),
    ('get_local_descriptor', {'owner': None, 'repo': None}),
])
def test_get_deletions(monkeypatch, mocked_function, kwargs):
    """Resources present in the previous descriptor but not in the new files are deletions."""
    descriptor = b'{"resources": [{"path": "old_file.csv"}, {"path": "removed_file.csv"}]}'
    monkeypatch.setattr(github, mocked_function, lambda *a, **k: descriptor)

    files = {'current_file.csv': b'', 'datapackage.json': b''}
    deletions = github.get_deletions('token', files, **kwargs)

    assert deletions == {'old_file.csv', 'removed_file.csv'}


def test_get_deletions_no_previous_descriptor(monkeypatch):
    """No previous descriptor (e.g. first-ever load) means nothing to delete."""
    monkeypatch.setattr(github, 'get_remote_descriptor', lambda *a, **k: None)

    files = {'current_file.csv': b'', 'datapackage.json': b''}
    deletions = github.get_deletions('token', files, owner='owner', repo='repo')

    assert deletions == set()
