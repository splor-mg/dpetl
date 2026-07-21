"""
Integration tests for extraction module: email and API sources.
"""
import pytest
import requests

from dpetl.extract import api, email, extract


# Helper: Mock for IMAP MailBox ------------------------------------------------
class MockFolder:
    """Mock for IMAP folder with set() method."""
    def set(self, folder):
        pass


class MockMailBox:
    """
    Mock for imap_tools.MailBox that returns a dummy email with attachments.
    """
    def __init__(self, *args, **kwargs):
        self.folder = MockFolder()

    def login(self, user, pwd):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def fetch(self, criteria, limit, reverse):
        # Create a dummy message with a single attachment
        class Msg:
            subject = 'test'
            date = '2026-07-16'
            from_ = 'sender'
            attachments = [type('Att', (), {'filename': 'file.csv', 'payload': b'content'})]
        return [Msg()]


# Tests for extract_package (dispatcher) ---------------------------------------
def test_extract_package_email_mode(fake_package, monkeypatch):
    """
    Verify that extract_package calls email_connection when mode is 'email'.
    """
    calls = []

    def fake_email_connection(resource, **kwargs):
        calls.append(resource.name)

    monkeypatch.setattr('dpetl.extract.email.email_connection', fake_email_connection)

    from dpetl.extract import extract
    extract.extract_package(fake_package, no_stop=True, no_validate=True)

    assert calls == ['test_resource']


def test_extract_package_api_mode(monkeypatch):
    """
    Verify that extract_package calls check_multipart_files when mode is 'api'.
    """
    calls = []

    def fake_api(resource, **kwargs):
        calls.append(('api', resource.name))

    monkeypatch.setattr('dpetl.extract.api.check_multipart_files', fake_api)

    # Minimal resource and package with mode='api'
    class FakeResource:
        name = 'test_resource'
        custom = {'dpetl_extract': {'mode': 'api'}}
        extrapaths = []

    class FakePackage:
        resources = [FakeResource()]

    extract.extract_package(FakePackage(), no_stop=True, no_validate=True)

    assert calls == [('api', 'test_resource')]


# Tests for email_connection (direct) ------------------------------------------
def test_email_connection_missing_env(monkeypatch, caplog):
    """
    Ensure SystemExit is raised when required environment variables are missing.
    """
    monkeypatch.delenv('EMAIL_USER', raising=False)
    monkeypatch.delenv('EMAIL_PWD', raising=False)
    monkeypatch.delenv('EMAIL_IMAP', raising=False)

    resource = type('Resource', (), {'custom': {'dpetl_extract': {}}, 'extrapaths': []})()

    with pytest.raises(SystemExit):
        email.email_connection(resource)

    assert 'Missing one of the required e-mail environment variables' in caplog.text


def test_email_connection_success(monkeypatch, tmp_path):
    """
    Test successful email connection and attachment saving.
    """
    monkeypatch.setenv('EMAIL_USER', 'user')
    monkeypatch.setenv('EMAIL_PWD', 'pass')
    monkeypatch.setenv('EMAIL_IMAP', 'imap.host')

    # Disable proxy configuration to avoid side effects
    monkeypatch.setattr('dpetl.extract.email.configure_proxy_from_env', lambda: None)

    # Apply MailBox mock globally
    monkeypatch.setattr('imap_tools.MailBox', MockMailBox)
    monkeypatch.setattr('dpetl.extract.email.MailBox', MockMailBox)

    # Create a minimal resource with 'name'
    resource = type('Resource', (), {
        'name': 'test_resource',
        'custom': {'dpetl_extract': {'criteria': {'subject': 'test'}}},
        'extrapaths': [],
        'path': 'output/file.csv',
        'package': type('Package', (), {'name': 'pkg', '_basepath': str(tmp_path)})()
    })()

    from dpetl.extract import email
    email.email_connection(resource)

    # Verify file was created
    saved_file = tmp_path / 'output/file.csv'
    assert saved_file.exists()
    assert saved_file.read_bytes() == b'content'


def test_email_connection_with_extrapaths(monkeypatch, tmp_path):
    """
    Test email connection when resource has extrapaths.
    Should save attachment to both main path and each extrapath.
    """
    monkeypatch.setenv('EMAIL_USER', 'user')
    monkeypatch.setenv('EMAIL_PWD', 'pass')
    monkeypatch.setenv('EMAIL_IMAP', 'imap.host')
    monkeypatch.setattr('dpetl.extract.email.configure_proxy_from_env', lambda: None)

    # Use the same MailBox mock
    monkeypatch.setattr('imap_tools.MailBox', MockMailBox)
    monkeypatch.setattr('dpetl.extract.email.MailBox', MockMailBox)

    # Create resource with 'name' and extrapaths
    resource = type('Resource', (), {
        'name': 'test_resource',
        'custom': {'dpetl_extract': {'criteria': {'subject': 'test'}}},
        'extrapaths': ['output/extra.csv'],
        'path': 'output/file.csv',
        'package': type('Package', (), {'name': 'pkg', '_basepath': str(tmp_path)})()
    })()

    from dpetl.extract import email
    email.email_connection(resource)

    # Both files should exist
    assert (tmp_path / 'output/file.csv').exists()
    assert (tmp_path / 'output/extra.csv').exists()


# Tests for API extraction -----------------------------------------------------
def test_check_multipart_files(monkeypatch, tmp_path):
    """
    Test check_multipart_files: downloads from API and saves to path and extrapaths.
    """
    # Mock requests.get to return dummy content
    class MockResponse:
        def __init__(self, content):
            self.content = content
            self.headers = {'content-length': str(len(content))}

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield self.content

    def mock_get(url, **kwargs):
        return MockResponse(b'dado,teste\n1,2')

    monkeypatch.setattr(requests, 'get', mock_get)

    # Create resource with paths inside tmp_path
    resource = type('Resource', (), {
        'name': 'test',
        'path': str(tmp_path / 'data/file.csv'),
        'sources': [{'method': 'GET', 'path': 'https://api.example.com/file.csv'}],
        'extrapaths': [str(tmp_path / 'data/file2.csv')]
    })()

    # Ensure the parent directory exists
    (tmp_path / 'data').mkdir(parents=True, exist_ok=True)

    api.check_multipart_files(resource, no_validate=True)

    # Both files should be created
    assert (tmp_path / 'data/file.csv').exists()
    assert (tmp_path / 'data/file2.csv').exists()


def test_extract_api_error(monkeypatch):
    """
    Test that extract_api raises RequestException when the HTTP request fails.
    """
    def mock_get(*args, **kwargs):
        raise requests.exceptions.RequestException('Falha')

    monkeypatch.setattr(requests, 'get', mock_get)

    resource = type('Resource', (), {
        'sources': [{'method': 'GET', 'path': 'http://fail.com'}],
        'path': 'out.csv'
    })()

    with pytest.raises(requests.exceptions.RequestException):
        api.extract_api(resource)
