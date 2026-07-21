"""
Unit tests for network helper functions: force_ipv4 and configure_proxy_from_env.
"""
import socket
import pytest

from dpetl.helpers import network


# Tests for force_ipv4 ---------------------------------------------------------
def test_force_ipv4(monkeypatch):
    """Test that force_ipv4 replaces getaddrinfo with a wrapper."""
    original = socket.getaddrinfo
    network.force_ipv4()
    assert socket.getaddrinfo.__name__ == 'getaddrinfo_ipv4'
    socket.getaddrinfo = original


def test_force_ipv4_wrapper_uses_af_inet(monkeypatch):
    """Test that the wrapper calls the original with AF_INET."""
    original = socket.getaddrinfo
    called_with_family = []

    def fake_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        called_with_family.append(family)
        return []

    monkeypatch.setattr(socket, 'getaddrinfo', fake_getaddrinfo)
    network.force_ipv4()
    socket.getaddrinfo('localhost', 80)
    socket.getaddrinfo = original
    assert called_with_family == [socket.AF_INET]


# Tests for configure_proxy_from_env -------------------------------------------
@pytest.mark.parametrize(('env_var', 'url', 'expected_type', 'expected_addr', 'expected_port', 'expected_user', 'expected_pass'), [
    ('HTTP_PROXY', 'http://proxy:8080', 'http', 'proxy', 8080, None, None),
    ('HTTP_PROXY', 'http://user:pass@proxy:8080', 'http', 'proxy', 8080, 'user', 'pass'),
    ('HTTP_PROXY', 'socks5://socks:1080', 'socks5', 'socks', 1080, None, None),
    ('HTTPS_PROXY', 'http://proxy:8080', 'http', 'proxy', 8080, None, None),
    ('http_proxy', 'http://proxy:8080', 'http', 'proxy', 8080, None, None),
])
def test_configure_proxy_from_env(monkeypatch, env_var, url, expected_type, expected_addr, expected_port, expected_user, expected_pass):
    """
    Test proxy configuration with different URL formats and environment variable names.
    """
    import socks

    if env_var == 'http_proxy':
        monkeypatch.delenv('HTTP_PROXY', raising=False)
        monkeypatch.delenv('HTTPS_PROXY', raising=False)

    monkeypatch.setenv(env_var, url)
    proxy_args = []

    def mock_set_default_proxy(proxy_type, addr, port, username=None, password=None):
        proxy_args.append((proxy_type, addr, port, username, password))

    monkeypatch.setattr(socks, 'set_default_proxy', mock_set_default_proxy)
    monkeypatch.setattr(network, 'force_ipv4', lambda: None)

    network.configure_proxy_from_env()

    assert len(proxy_args) == 1
    proxy_type, addr, port, username, password = proxy_args[0]

    expected_type_map = {
        'http': socks.HTTP,
        'socks5': socks.SOCKS5,
    }
    expected_proxy_type = expected_type_map[expected_type]

    assert proxy_type == expected_proxy_type
    assert addr == expected_addr
    assert port == expected_port
    assert username == expected_user
    assert password == expected_pass


def test_configure_proxy_from_env_no_proxy(monkeypatch):
    """Test that function returns early when no proxy is set."""
    import socks
    monkeypatch.delenv('HTTP_PROXY', raising=False)
    monkeypatch.delenv('HTTPS_PROXY', raising=False)
    monkeypatch.delenv('http_proxy', raising=False)
    monkeypatch.delenv('https_proxy', raising=False)

    called = False

    def mock_set_default_proxy(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(socks, 'set_default_proxy', mock_set_default_proxy)
    monkeypatch.setattr(network, 'force_ipv4', lambda: None)

    network.configure_proxy_from_env()

    assert called is False
