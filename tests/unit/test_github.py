"""
Unit tests for the github module: installation tokens,
repository settings, descriptor retrieval, and deletion detection.
"""
import pytest
import base64
import requests
import subprocess

from dpetl.load import github


def test_get_installation_token_missing_dependencies(monkeypatch):
    """Test that ImportError is raised if PyJWT is not installed."""
    monkeypatch.setitem(__import__('sys').modules, 'jwt', None)
    with pytest.raises(ImportError, match="GitHub App authentication requires additional dependencies"):
        github.get_installation_token('123', 'key', 'owner')


def test_get_installation_token_with_installation_id(monkeypatch):
    """Test success with installation_id provided."""
    import jwt
    monkeypatch.setattr(jwt, 'encode', lambda *a, **k: 'fake_jwt')

    def mock_post(url, headers):
        class Resp:
            status_code = 201
            def json(self): return {'token': 'fake_install_token'}
            def raise_for_status(self): pass
        return Resp()

    monkeypatch.setattr(requests, 'post', mock_post)
    token = github.get_installation_token('123', 'key', 'owner', '456')
    assert token == 'fake_install_token'


def test_get_installation_token_auto_discovery(monkeypatch):
    """Test automatic discovery of installation_id."""
    import jwt
    monkeypatch.setattr(jwt, 'encode', lambda *a, **k: 'fake_jwt')

    calls = []
    def mock_get(url, headers):
        calls.append(('GET', url))
        class Resp:
            status_code = 200
            def json(self): return {'id': 789}
            def raise_for_status(self): pass
        return Resp()

    def mock_post(url, headers):
        calls.append(('POST', url))
        class Resp:
            status_code = 201
            def json(self): return {'token': 'fake_token'}
            def raise_for_status(self): pass
        return Resp()

    monkeypatch.setattr(requests, 'get', mock_get)
    monkeypatch.setattr(requests, 'post', mock_post)

    github.get_installation_token('123', 'key', 'owner')
    assert ('GET', 'https://api.github.com/orgs/owner/installation') in calls
    assert ('POST', 'https://api.github.com/app/installations/789/access_tokens') in calls


def test_get_installation_token_request_failure(monkeypatch):
    """Test error when the request fails."""
    import jwt
    monkeypatch.setattr(jwt, 'encode', lambda *a, **k: 'fake_jwt')

    def mock_get(*args, **kwargs):
        class Resp:
            status_code = 404
            def raise_for_status(self): raise requests.exceptions.HTTPError()
        return Resp()

    monkeypatch.setattr(requests, 'get', mock_get)
    with pytest.raises(requests.exceptions.HTTPError):
        github.get_installation_token('123', 'key', 'owner')


def test_get_repo_settings_valid():
    """Test get_repo_settings with valid configuration."""
    package = type('Package', (), {
        'custom': {
            'dpetl_load': {
                'owner': 'test',
                'repo': 'repo',
                'level': 'orgs',
                'visibility': 'public'
            }
        }
    })()

    settings = github.get_repo_settings(package)
    assert settings['owner'] == 'test'
    assert settings['repo'] == 'repo'
    assert settings['level'] == 'orgs'
    assert settings['visibility'] == 'public'


def test_get_repo_settings_missing_owner():
    """Test get_repo_settings raises SystemExit when repo is set but owner is missing."""
    package = type('Package', (), {
        'custom': {'dpetl_load': {'repo': 'repo'}}
    })()

    with pytest.raises(SystemExit):
        github.get_repo_settings(package)


def test_get_repo_settings_invalid_level():
    """Test get_repo_settings raises SystemExit for invalid level."""
    package = type('Package', (), {
        'custom': {'dpetl_load': {'owner': 'test', 'repo': 'repo', 'level': 'invalid'}}
    })()

    with pytest.raises(SystemExit):
        github.get_repo_settings(package)


def test_get_repo_settings_invalid_visibility():
    """Test get_repo_settings raises SystemExit for invalid visibility."""
    package = type('Package', (), {
        'custom': {'dpetl_load': {'owner': 'test', 'repo': 'repo', 'visibility': 'invalid'}}
    })()

    with pytest.raises(SystemExit):
        github.get_repo_settings(package)


def test_get_remote_descriptor_not_found(monkeypatch):
    """Test get_remote_descriptor returns None when descriptor does not exist."""
    def mock_get(url, headers):
        class Resp:
            status_code = 404
        return Resp()

    monkeypatch.setattr(requests, 'get', mock_get)
    result = github.get_remote_descriptor('owner', 'repo', 'token')
    assert result is None


def test_get_remote_descriptor_success(monkeypatch):
    """Test get_remote_descriptor returns decoded content."""
    def mock_get(url, headers):
        class Resp:
            status_code = 200

            def json(self):
                return {'content': base64.b64encode(b'{"resources": []}').decode()}

            def raise_for_status(self):
                pass
        return Resp()

    monkeypatch.setattr(requests, 'get', mock_get)
    result = github.get_remote_descriptor('owner', 'repo', 'token')
    assert result == b'{"resources": []}'


def test_get_local_descriptor_success(monkeypatch):
    """Test get_local_descriptor returns content when git show succeeds."""
    def mock_run(cmd, capture_output=True):
        class CompletedProcess:
            returncode = 0
            stdout = b'{"resources": []}'
        return CompletedProcess()

    monkeypatch.setattr(subprocess, 'run', mock_run)
    result = github.get_local_descriptor()
    assert result == b'{"resources": []}'


def test_get_local_descriptor_not_found(monkeypatch):
    """Test get_local_descriptor returns None when git show fails."""
    def mock_run(cmd, capture_output=True):
        class CompletedProcess:
            returncode = 128
            stdout = b''
        return CompletedProcess()

    monkeypatch.setattr(subprocess, 'run', mock_run)
    result = github.get_local_descriptor()
    assert result is None


def test_get_deletions_remote(monkeypatch):
    """Test get_deletions identifies removed resources from remote."""
    def mock_get_remote_descriptor(*args):
        return b'{"resources": [{"path": "old_file.csv"}, {"path": "removed_file.csv"}]}'

    monkeypatch.setattr(github, 'get_remote_descriptor', mock_get_remote_descriptor)

    files = {'current_file.csv': b'', 'datapackage.json': b''}
    deletions = github.get_deletions('token', files, owner='owner', repo='repo')
    assert deletions == {'old_file.csv', 'removed_file.csv'}


def test_get_deletions_local(monkeypatch):
    """Test get_deletions identifies removed resources from local."""
    def mock_get_local_descriptor():
        return b'{"resources": [{"path": "old_file.csv"}, {"path": "removed_file.csv"}]}'

    monkeypatch.setattr(github, 'get_local_descriptor', mock_get_local_descriptor)

    files = {'current_file.csv': b'', 'datapackage.json': b''}
    deletions = github.get_deletions('token', files, owner=None, repo=None)
    assert deletions == {'old_file.csv', 'removed_file.csv'}
