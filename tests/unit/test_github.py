import pytest
import requests
from dpetl.load import github


def test_get_installation_token_missing_dependencies(monkeypatch):
    """Testa que ImportError é levantado se PyJWT não estiver instalado."""
    monkeypatch.setitem(__import__('sys').modules, 'jwt', None)
    with pytest.raises(ImportError, match="GitHub App authentication requires additional dependencies"):
        github.get_installation_token('123', 'key', 'owner')


def test_get_installation_token_with_installation_id(monkeypatch):
    """Testa sucesso com installation_id fornecido."""
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
    """Testa descoberta automática do installation_id."""
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
    """Testa erro quando a requisição falha."""
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
