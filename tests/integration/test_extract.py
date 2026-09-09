"""
Integration tests for extraction module: email and API sources.
"""
import pytest
import requests
import subprocess
import logging
from types import SimpleNamespace

from dpetl.extract import api, command, email, extract


# Helper: Mock for IMAP MailBox ------------------------------------------------
class MockFolder:
    """Mock for IMAP folder with set() method."""
    def set(self, folder):
        pass


class MockMailBox:
    """Mock for imap_tools.MailBox that returns a dummy email with attachments."""
    def __init__(self, *args, **kwargs):
        self.folder = MockFolder()

    def login(self, user, pwd):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def fetch(self, criteria, limit, reverse):
        class Msg:
            subject = 'test'
            date = '2026-07-16'
            from_ = 'sender'
            attachments = [type('Att', (), {'filename': 'file.csv', 'payload': b'content'})]
        return [Msg()]


# Helpers for building fake resources/packages ---------------------------------
def make_fake_resource(mode, name='test_resource', custom_extra=None):
    custom = {'dpetl_extract': {'mode': mode}} if mode is not None else {}
    if custom_extra:
        custom['dpetl_extract'].update(custom_extra)
    return type('FakeResource', (), {
        'name': name,
        'custom': custom,
        'extrapaths': []
    })


def make_fake_package(resources):
    return type('FakePackage', (), {'resources': resources})()


def make_email_resource(tmp_path, extrapaths=None):
    return type('Resource', (), {
        'name': 'test_resource',
        'custom': {'dpetl_extract': {'criteria': {'subject': 'test'}}},
        'extrapaths': extrapaths or [],
        'path': 'output/file.csv',
        'package': type('Package', (), {'name': 'pkg', '_basepath': str(tmp_path)})()
    })()


# extract_package (dispatcher) -------------------------------------------------
def test_extract_package_missing_mode(caplog):
    """When resource has no dpetl_extract.mode, log error and return."""
    resource = make_fake_resource(None)
    package = make_fake_package([resource])

    extract.extract_package(package, no_stop=True, no_validate=True)

    assert 'Missing required dpetl_extract.mode' in caplog.text


@pytest.mark.parametrize('mode, mock_path, expected', [
    ('email', 'dpetl.extract.email.email_connection', 'test_resource'),
    ('api', 'dpetl.extract.api.check_multipart_files', ('api', 'test_resource')),
    ('cli', 'dpetl.extract.command.check_cli_commands', ('cli', 'test_resource')),
])
def test_extract_package_modes(monkeypatch, mode, mock_path, expected):
    """extract_package dispatches to the correct extractor based on mode."""
    calls = []

    def fake_func(resource, **kwargs):
        calls.append(resource.name if mode == 'email' else (mode, resource.name))

    monkeypatch.setattr(mock_path, fake_func)

    resource = make_fake_resource(mode)
    package = make_fake_package([resource])

    extract.extract_package(package, no_stop=True, no_validate=True)

    assert calls == [expected]


@pytest.mark.parametrize('check_resource_result, expected_sleep_calls', [
    (True, [2]),
    (False, []),
])
def test_extract_package_delay_and_validation(monkeypatch, check_resource_result, expected_sleep_calls):
    """
    time.sleep(delay) only runs after a resource that passes validation; the
    loop breaks immediately (before sleeping) once validation fails.
    """
    sleep_calls = []
    monkeypatch.setattr('dpetl.extract.extract.time.sleep', lambda s: sleep_calls.append(s))
    monkeypatch.setattr('dpetl.extract.extract.validate.check_resource', lambda *a, **k: check_resource_result)
    monkeypatch.setattr('dpetl.extract.email.email_connection', lambda *a, **k: None)

    package = make_fake_package([make_fake_resource('email')])
    extract.extract_package(package, delay=2, no_stop=True, no_validate=True)

    assert sleep_calls == expected_sleep_calls


# email_connection -------------------------------------------------------------
def test_email_connection_missing_env(monkeypatch, caplog):
    """SystemExit is raised when required environment variables are missing."""
    monkeypatch.delenv('EMAIL_USER', raising=False)
    monkeypatch.delenv('EMAIL_PWD', raising=False)
    monkeypatch.delenv('EMAIL_IMAP', raising=False)

    resource = type('Resource', (), {'custom': {'dpetl_extract': {}}, 'extrapaths': []})()

    with pytest.raises(SystemExit):
        email.email_connection(resource)

    assert 'Missing one of the required e-mail environment variables' in caplog.text


@pytest.mark.parametrize('extrapaths', [
    [],
    ['output/extra.csv'],
])
def test_email_connection_saves_attachment(monkeypatch, tmp_path, extrapaths):
    """The attachment is saved to the resource's path, and to any extrapaths too."""
    monkeypatch.setenv('EMAIL_USER', 'user')
    monkeypatch.setenv('EMAIL_PWD', 'pass')
    monkeypatch.setenv('EMAIL_IMAP', 'imap.host')
    monkeypatch.setattr('dpetl.extract.email.configure_proxy_from_env', lambda: None)
    monkeypatch.setattr('imap_tools.MailBox', MockMailBox)
    monkeypatch.setattr('dpetl.extract.email.MailBox', MockMailBox)

    resource = make_email_resource(tmp_path, extrapaths=extrapaths)
    email.email_connection(resource)

    assert (tmp_path / 'output/file.csv').read_bytes() == b'content'
    for extra in extrapaths:
        assert (tmp_path / extra).exists()


# API extraction ---------------------------------------------------------------
def test_check_multipart_files(monkeypatch, tmp_path):
    """check_multipart_files downloads from the API and saves to path and extrapaths."""
    content = b'dado,teste\n1,2'
    response = SimpleNamespace(
        content=content,
        headers={'content-length': str(len(content))},
        raise_for_status=lambda: None,
        iter_content=lambda chunk_size: iter([content]),
    )
    monkeypatch.setattr(requests, 'get', lambda url, **k: response)

    (tmp_path / 'data').mkdir(parents=True, exist_ok=True)
    resource = type('Resource', (), {
        'name': 'test',
        'path': str(tmp_path / 'data/file.csv'),
        'sources': [{'method': 'GET', 'path': 'https://api.example.com/file.csv'}],
        'extrapaths': [str(tmp_path / 'data/file2.csv')]
    })()

    api.check_multipart_files(resource, no_validate=True)

    assert (tmp_path / 'data/file.csv').exists()
    assert (tmp_path / 'data/file2.csv').exists()


def test_extract_api_error(monkeypatch):
    """extract_api raises RequestException when the HTTP request fails."""
    def mock_get(*a, **k):
        raise requests.exceptions.RequestException('Falha')
    monkeypatch.setattr(requests, 'get', mock_get)

    resource = type('Resource', (), {
        'sources': [{'method': 'GET', 'path': 'http://fail.com'}],
        'path': 'out.csv'
    })()

    with pytest.raises(requests.exceptions.RequestException):
        api.extract_api(resource)


# CLI extraction ---------------------------------------------------------------
def test_check_cli_commands_missing_arguments(caplog):
    """check_cli_commands logs an error when arguments are missing."""
    resource = type('Resource', (), {'name': 'test', 'custom': {'dpetl_extract': {}}})()

    command.check_cli_commands(resource)

    assert 'Missing required dpetl_extract.arguments' in caplog.text


def test_check_cli_commands_success(monkeypatch, caplog):
    """check_cli_commands runs every configured argument."""
    caplog.set_level(logging.DEBUG)
    resource = type('Resource', (), {
        'name': 'test',
        'custom': {'dpetl_extract': {'arguments': ['echo "hello"', 'ls -l']}}
    })()
    monkeypatch.setattr(subprocess, 'run', lambda cmd, **k: type('CompletedProcess', (), {'returncode': 0})())

    command.check_cli_commands(resource)

    assert 'Running command' in caplog.text
    assert 'CLI command failed' not in caplog.text


@pytest.mark.parametrize('exception, expected_log', [
    (subprocess.CalledProcessError(1, 'false'), 'CLI command failed for resource test:'),
    (FileNotFoundError("No such file: 'nonexistent'"), "CLI command not found for resource test: No such file: 'nonexistent'"),
])
def test_run_cli_command_errors(monkeypatch, caplog, exception, expected_log):
    """run_cli_command logs a failed or missing command instead of letting it propagate."""
    def fake_run(cmd, check=True):
        raise exception
    monkeypatch.setattr(subprocess, 'run', fake_run)

    command.run_cli_command('cmd', type('Resource', (), {'name': 'test'})())

    assert expected_log in caplog.text
