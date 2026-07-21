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
