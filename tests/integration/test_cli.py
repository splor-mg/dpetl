"""
Integration tests for CLI commands: extract, transform, load, linktable.
Tests both command dispatching (via mocks) and the full integration flow.
"""
import re
import shutil
import logging
import pytest
from typer.testing import CliRunner

from dpetl.cli import app

runner = CliRunner()


# CLI dispatch tests (using mocks) ---------------------------------------------
@pytest.mark.parametrize('args, expected', [
    (['--today-email', '--add-package-name'], {'today_email': True, 'add_package_name': True}),
    ([], {'today_email': False, 'add_package_name': False, 'delay': 0}),
    (['--delay', '10'], {'delay': 10}),
])
def test_extract_command_flags(mock_descriptor_iteration, args, expected):
    """extract dispatches to descriptor_iteration with the given flags."""
    result = runner.invoke(app, ['extract'] + args, obj={'no_validate': True, 'no_stop': True})

    assert result.exit_code == 0
    kwargs = mock_descriptor_iteration[0]
    assert kwargs['operation'] == 'extract'
    assert kwargs.get('descriptor') is None
    for key, value in expected.items():
        assert kwargs[key] == value


@pytest.mark.parametrize('command', ['transform', 'load', 'linktable'])
def test_command_calls_descriptor_iteration(mock_descriptor_iteration, command):
    """transform/load/linktable dispatch to descriptor_iteration with the matching operation."""
    result = runner.invoke(app, [command], obj={'no_validate': True, 'no_stop': True})

    assert result.exit_code == 0
    kwargs = mock_descriptor_iteration[0]
    assert kwargs['operation'] == command
    assert kwargs.get('descriptor') is None


def test_transform_keygen_command():
    """The keygen subcommand generates a valid 64-char hex secret key."""
    result = runner.invoke(app, ['transform', 'keygen'])

    assert result.exit_code == 0
    output = result.output.strip()
    assert output.startswith('ANONYMIZE_SECRET_KEY=')
    key = output.split('=')[1]
    assert len(key) == 64
    assert all(c in '0123456789abcdef' for c in key)


# Version/help flags -----------------------------------------------------------
def test_version_flag():
    """--version displays the version string."""
    result = runner.invoke(app, ['--version'])

    assert result.exit_code == 0
    assert re.match(r'dpetl \d+\.\d+\.\d+', result.output.strip()) is not None


def test_help_flag():
    """--help displays usage and the list of commands."""
    result = runner.invoke(app, ['--help'])

    assert result.exit_code == 0
    assert 'Usage' in result.output
    assert 'Commands' in result.output or 'extract' in result.output


# Integration test with real files ---------------------------------------------
def test_extract_integration(tmp_path):
    """
    Full integration test: copy the shared datapackage.yaml, create the dummy
    data files the 'acao' resource expects, and run the extract command.
    """
    shutil.copy('tests/datapackage/datapackage.yaml', tmp_path / 'datapackage.yaml')

    data_raw_dir = tmp_path / 'data_raw'
    data_raw_dir.mkdir()
    (data_raw_dir / 'acao_previous.csv').write_text('ano,acao_cod,acao_desc\n2024,001,Teste')
    (data_raw_dir / 'acao_current.csv').write_text('ano,acao_cod,acao_desc\n2025,002,Teste2')

    result = runner.invoke(app, ['extract'], obj={'no_validate': True, 'no_stop': True})

    assert result.exit_code == 0


# Logging flags ----------------------------------------------------------------
def test_verbose_and_quiet_conflict():
    """--verbose and --quiet cannot be used together."""
    result = runner.invoke(app, ['--verbose', '--quiet', 'extract'])

    assert result.exit_code == 2
    assert 'cannot be used together' in result.output


def test_verbose_creates_log_file(tmp_path, monkeypatch):
    """--verbose creates a debug log file."""
    monkeypatch.chdir(tmp_path)

    runner.invoke(app, ['--verbose', 'extract'], obj={'no_validate': True, 'no_stop': True})

    assert (tmp_path / 'dpetl.debug.log').exists()


def test_quiet_does_not_create_log_file(tmp_path, monkeypatch):
    """--quiet does not create a debug log file."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ['--help', '--quiet'])

    assert result.exit_code == 0
    assert not (tmp_path / 'dpetl.debug.log').exists()


@pytest.mark.parametrize('verbose, quiet, expected_level', [
    (True, False, logging.DEBUG),
    (False, False, logging.INFO),
    (False, True, logging.WARNING),
])
def test_logging_levels(monkeypatch, tmp_path, verbose, quiet, expected_level):
    """setup_logging sets the matching level for each verbose/quiet combination."""
    from dpetl.cli import setup_logging

    monkeypatch.chdir(tmp_path)
    logging.getLogger().handlers.clear()
    logging.getLogger().setLevel(logging.NOTSET)

    setup_logging(verbose=verbose, quiet=quiet)

    assert logging.getLogger().level == expected_level


# Validate flags ---------------------------------------------------------------
def test_validate_before_and_no_validate_conflict():
    """--validate-before and --no-validate cannot be used together."""
    result = runner.invoke(app, ['--validate-before', '--no-validate', 'transform'])

    assert result.exit_code == 2
    assert 'cannot be used together' in result.output


def test_validate_before_not_supported_for_extract():
    """--validate-before is not supported for the extract command."""
    result = runner.invoke(app, ['--validate-before', 'extract'])

    assert result.exit_code == 2
    assert 'not supported' in result.output and 'extract' in result.output
