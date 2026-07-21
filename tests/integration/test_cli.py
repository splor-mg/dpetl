"""
Integration tests for CLI commands: extract, transform, load.
Tests both command dispatching (via mocks) and the full integration flow.
"""
import re
import shutil
from typer.testing import CliRunner
from dpetl.cli import app

runner = CliRunner()


# CLI dispatch tests (using mocks) ---------------------------------------------
def test_extract_command_calls_descriptor_iteration(mock_descriptor_iteration):
    """
    Verify that the extract command calls descriptor_iteration with correct params.
    """
    result = runner.invoke(app, [
        'extract',
        '--today-email',
        '--add-package-name'
    ], obj={'no_validate': True, 'no_stop': True})

    assert result.exit_code == 0
    assert len(mock_descriptor_iteration) == 1
    kwargs = mock_descriptor_iteration[0]
    assert kwargs['operation'] == 'extract'
    assert kwargs.get('descriptor') is None
    assert kwargs['today_email'] is True
    assert kwargs['add_package_name'] is True


def test_transform_command_calls_descriptor_iteration(mock_descriptor_iteration):
    """
    Verify that the transform command calls descriptor_iteration with correct params.
    """
    result = runner.invoke(app, ['transform'], obj={'no_validate': True, 'no_stop': True})
    assert result.exit_code == 0
    kwargs = mock_descriptor_iteration[0]
    assert kwargs['operation'] == 'transform'
    assert kwargs.get('descriptor') is None


def test_load_command_calls_descriptor_iteration(mock_descriptor_iteration):
    """
    Verify that the load command calls descriptor_iteration with correct params.
    """
    result = runner.invoke(app, ['load'], obj={'no_validate': True, 'no_stop': True})
    assert result.exit_code == 0
    kwargs = mock_descriptor_iteration[0]
    assert kwargs['operation'] == 'load'
    assert kwargs.get('descriptor') is None


def test_extract_default_descriptor(mock_descriptor_iteration):
    """
    Verify that extract uses default descriptor discovery when none is provided.
    The descriptor param should be None, and flags default to False.
    """
    result = runner.invoke(app, ['extract'], obj={'no_validate': True, 'no_stop': True})
    assert result.exit_code == 0
    kwargs = mock_descriptor_iteration[0]
    assert kwargs.get('descriptor') is None
    assert kwargs['today_email'] is False
    assert kwargs['add_package_name'] is False


# Version flag test ------------------------------------------------------------
def test_version_flag():
    """
    Test the --version flag to ensure it displays the version correctly.
    """
    result = runner.invoke(app, ['--version'])
    assert result.exit_code == 0
    assert re.match(r'dpetl \d+\.\d+\.\d+', result.output.strip()) is not None


def test_help_flag():
    """
    Test the --help flag to ensure help text is displayed.
    """
    result = runner.invoke(app, ['--help'])
    assert result.exit_code == 0
    assert 'Usage' in result.output
    assert 'Commands' in result.output or 'extract' in result.output


# Integration test with real files ---------------------------------------------
def test_extract_integration(tmp_path):
    """
    Full integration test: copy a datapackage.yaml, create dummy data files,
    and run the extract command to verify the full flow works.
    """
    # Copy datapackage.yaml to temporary directory
    shutil.copy('tests/data/datapackage.yaml', tmp_path / 'datapackage.yaml')

    # Create dummy data files that the datapackage expects
    data_raw_dir = tmp_path / 'data_raw'
    data_raw_dir.mkdir()
    (data_raw_dir / 'acao_previous.csv').write_text('ano,acao_cod,acao_desc\n2024,001,Teste')
    (data_raw_dir / 'acao_current.csv').write_text('ano,acao_cod,acao_desc\n2025,002,Teste2')

    # Run the extract command
    result = runner.invoke(app, ['extract'], obj={'no_validate': True, 'no_stop': True})
    assert result.exit_code == 0


# Logging flags test -----------------------------------------------------------
def test_verbose_and_quiet_conflict():
    """Test that --verbose and --quiet cannot be used together."""
    result = runner.invoke(app, ['--verbose', '--quiet', 'extract'])
    assert result.exit_code == 2
    assert "cannot be used together" in result.output


def test_verbose_creates_log_file(tmp_path, monkeypatch):
    """Test that --verbose creates a debug log file."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ['--verbose', 'extract'], obj={'no_validate': True, 'no_stop': True})
    assert (tmp_path / 'dpetl.debug.log').exists()


def test_quiet_does_not_create_log_file(tmp_path, monkeypatch):
    """Test that --quiet does not create a debug log file."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ['--help', '--quiet'])
    assert result.exit_code == 0
    assert not (tmp_path / 'dpetl.debug.log').exists()


def test_verbose_sets_debug_level(monkeypatch, tmp_path):
    """Test that --verbose sets logging level to DEBUG."""
    import logging
    from dpetl.cli import setup_logging

    monkeypatch.chdir(tmp_path)

    logging.getLogger().handlers.clear()
    logging.getLogger().setLevel(logging.NOTSET)

    setup_logging(verbose=True, quiet=False)

    assert logging.getLogger().level == logging.DEBUG


def test_default_logging_level(monkeypatch, tmp_path):
    """Test that default logging level is INFO."""
    import logging
    from dpetl.cli import setup_logging

    monkeypatch.chdir(tmp_path)
    logging.getLogger().handlers.clear()
    logging.getLogger().setLevel(logging.NOTSET)

    setup_logging(verbose=False, quiet=False)
    assert logging.getLogger().level == logging.INFO


def test_quiet_sets_warning_level(monkeypatch, tmp_path):
    """Test that --quiet sets logging level to WARNING."""
    import logging
    from dpetl.cli import setup_logging

    monkeypatch.chdir(tmp_path)
    logging.getLogger().handlers.clear()
    logging.getLogger().setLevel(logging.NOTSET)

    setup_logging(verbose=False, quiet=True)
    assert logging.getLogger().level == logging.WARNING
