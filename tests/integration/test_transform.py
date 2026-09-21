"""
Integration tests for the transformation module.
"""
import pytest
import subprocess
import petl as etl
from frictionless import Package, Resource

from dpetl.transform import command, datapackage, transform


def mock_validation(monkeypatch):
    """Skip validation so transform_package tests focus on its own orchestration."""
    monkeypatch.setattr('dpetl.transform.transform.validate.validate_datapackage', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.validate.check_resource', lambda *a, **k: True)
    monkeypatch.setattr('dpetl.transform.transform.validate.validate_resources', lambda *a, **k: None)


@pytest.fixture(autouse=True)
def anonymize_secret_key(monkeypatch):
    """
    The 'anonymized' fixture resource has an aes_siv field, so any test that
    runs transform_package over the whole package needs this set, or it
    exits with 'Missing required environment variable'.
    """
    monkeypatch.setenv('ANONYMIZE_SECRET_KEY', '0123456789abcdef0123456789abcdef')


# Tests for transform_package --------------------------------------------------
def test_transform_package_orchestration(fake_package, monkeypatch):
    """
    transform_package runs, per resource: write_files, then update_metadata,
    then finally build_datapackage once at the end.
    """
    calls = []
    mock_validation(monkeypatch)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.write_files', lambda *a, **k: calls.append('write'))
    monkeypatch.setattr('dpetl.transform.transform.datapackage.update_metadata', lambda *a, **k: calls.append('update'))
    monkeypatch.setattr('dpetl.transform.transform.datapackage.build_datapackage', lambda *a, **k: calls.append('build'))

    transform.transform_package(fake_package)

    assert calls == ['write', 'update', 'build']


def test_transform_package_renames_target_fields(dpetl_package, scoped_package, monkeypatch):
    """Fields with a 'target' get renamed in the output table."""
    mock_validation(monkeypatch)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.write_files', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.update_metadata', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.build_datapackage', lambda *a, **k: None)

    rename_calls = []

    def fake_rename(table, old_name, new_name):
        rename_calls.append((old_name, new_name))
        return table
    monkeypatch.setattr('dpetl.transform.transform.etl.rename', fake_rename)

    package = scoped_package(dpetl_package, 'renamed')
    transform.transform_package(package)

    assert rename_calls == [('col1', 'nova_col1')]


def test_transform_package_anonymizes_fields(dpetl_package, scoped_package, monkeypatch, caplog):
    """Fields with an 'anonymize' config get anonymized, logging the operation."""
    caplog.set_level('DEBUG')

    mock_validation(monkeypatch)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.write_files', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.update_metadata', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.build_datapackage', lambda *a, **k: None)

    package = scoped_package(dpetl_package, 'anonymized')
    transform.transform_package(package)

    assert 'Anonymizing field' in caplog.text


def test_transform_package_stops_on_invalid_resource(dpetl_package, monkeypatch):
    """The loop stops right after the first resource that fails validation."""
    monkeypatch.setattr('dpetl.transform.transform.validate.validate_datapackage', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.validate.validate_resources', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.validate.check_resource', lambda *a, **k: False)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.update_metadata', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.build_datapackage', lambda *a, **k: None)

    write_calls = []
    monkeypatch.setattr('dpetl.transform.transform.datapackage.write_files', lambda *a, **k: write_calls.append('write'))

    transform.transform_package(dpetl_package)

    assert write_calls == ['write']


def test_transform_package_runs_cli(dpetl_package, scoped_package, monkeypatch):
    """When dpetl_transform.cli is set, check_cli_commands runs for that resource."""
    mock_validation(monkeypatch)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.write_files', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.update_metadata', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.build_datapackage', lambda *a, **k: None)

    cli_calls = []
    monkeypatch.setattr(
        'dpetl.transform.transform.command.check_cli_commands',
        lambda resource, table, **k: cli_calls.append(resource.name)
    )

    package = scoped_package(dpetl_package, 'cli_resource')
    transform.transform_package(package)

    assert cli_calls == ['cli_resource']


# Tests for get_output_settings ------------------------------------------------
def test_get_output_settings_full_config():
    """Every dpetl_transform property present is used as-is."""
    resource = type('Resource', (), {'custom': {'dpetl_transform': {
        'path': 'custom_data',
        'format': 'csv.gz',
        'encoding': 'latin1',
        'delimiter': ';',
    }}})()

    assert datapackage.get_output_settings(resource) == {
        'path': 'custom_data',
        'format': 'csv',
        'compression': 'gz',
        'extension': 'csv.gz',
        'encoding': 'latin1',
        'delimiter': ';',
        'cli': None,
        'pre_process': True,
        'stdin': False,
    }


def test_get_output_settings_defaults():
    """No dpetl_transform property present falls back to defaults."""
    resource = type('Resource', (), {'custom': {}})()

    assert datapackage.get_output_settings(resource) == {
        'path': 'data',
        'format': 'csv',
        'compression': 'gz',
        'extension': 'csv.gz',
        'encoding': 'utf-8',
        'delimiter': ',',
        'cli': None,
        'pre_process': True,
        'stdin': False,
    }


def test_get_output_settings_cli_pre_process():
    """dpetl_transform.cli.pre_process is surfaced directly on the settings."""
    resource = type('Resource', (), {'custom': {'dpetl_transform': {
        'cli': {'arguments': ['echo ok'], 'pre_process': False}
    }}})()

    settings = datapackage.get_output_settings(resource)
    assert settings['cli'] == {'arguments': ['echo ok'], 'pre_process': False}
    assert settings['pre_process'] is False


# Tests for write_files --------------------------------------------------------
class FakePackage:
    def __init__(self, basepath):
        self._basepath = basepath


class FakeResource:
    name = 'test'


@pytest.mark.parametrize(('format', 'extension'), [
    ('csv', 'csv'),
    ('txt', 'txt'),
    ('xlsx', 'xlsx'),
])
def test_write_files_formats(tmp_path, format, extension):
    """write_files produces a file for each supported format."""
    if format == 'xlsx':
        pytest.importorskip('openpyxl')

    table = etl.wrap([['col1', 'col2'], ['a', 'b']])
    datapackage.write_files(FakePackage(str(tmp_path)), FakeResource(), table, 'data', format, extension, 'utf-8', ',')

    assert (tmp_path / 'data' / f'test.{extension}').exists()


def test_write_files_unsupported_format():
    """An unrecognized format raises ValueError instead of writing anything."""
    table = etl.wrap([['col1', 'col2'], ['a', 'b']])

    with pytest.raises(ValueError, match='Unsupported format'):
        datapackage.write_files(
            FakePackage('/tmp'), FakeResource(), table,
            'data', 'unsupported', 'unsupported', 'utf-8', ','
        )


# Tests for update_metadata (built-in pipeline) --------------------------------
@pytest.mark.parametrize('compression, expected_path', [
    (None, 'processed/basic.csv'),
    ('gz', 'processed/basic.csv.gz'),
])
def test_update_metadata_deterministic(dpetl_package, monkeypatch, compression, expected_path):
    """Without 'cli', path/format/compression are built from the given settings."""
    resource = dpetl_package.get_resource('basic')
    monkeypatch.setattr(resource, 'infer', lambda *a, **k: None)
    extension = 'csv.gz' if compression else 'csv'

    datapackage.update_metadata(resource, 'processed', 'csv', compression, extension, ',', cli=None)

    assert resource.path == expected_path
    if compression:
        assert resource.compression == compression
        assert resource.format == 'csv'


def test_update_metadata_builds_anonymize_constraints(dpetl_package, monkeypatch):
    """A field's anonymize config produces a matching regex constraint."""
    resource = dpetl_package.get_resource('anonymized')
    monkeypatch.setattr(resource, 'infer', lambda *a, **k: None)

    datapackage.update_metadata(resource, 'processed', 'csv', None, 'csv', ',', cli=None)

    assert resource.schema.fields[0].constraints['pattern'] == '^[0-9a-f]{16}$'


# Tests for update_metadata (cli) ----------------------------------------------
def test_update_metadata_with_cli(tmp_path):
    """When 'cli' is set, the resource is (re-)inferred from the file it points to."""
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    (data_dir / 'test.csv').write_text('col1\nvalor1\n', encoding='utf-8')

    resource = Resource.from_descriptor({
        'name': 'test',
        'path': 'data/test.csv',
        'schema': {'fields': [{'name': 'col1', 'type': 'string'}]},
    }, basepath=str(tmp_path))
    package = Package(resources=[resource], basepath=str(tmp_path))
    resource = package.resources[0]

    datapackage.update_metadata(
        resource, path='data', format='csv', compression='gz',
        extension='csv.gz', delimiter=',', cli={'path': 'data'}
    )

    assert resource.path == 'data/test.csv'
    assert resource.format == 'csv'


def test_update_metadata_with_cli_non_table_falls_back_to_format(tmp_path):
    """When the located file isn't recognized as tabular, it's retried with the configured format."""
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    (data_dir / 'test.log').write_text('free text\nnot a table\n', encoding='utf-8')

    resource = Resource.from_descriptor({
        'name': 'test',
        'path': 'data/test.log',
        'schema': {'fields': [{'name': 'col1', 'type': 'string'}]},
    }, basepath=str(tmp_path))
    package = Package(resources=[resource], basepath=str(tmp_path))
    resource = package.resources[0]

    datapackage.update_metadata(
        resource, path='data', format='csv', compression=None,
        extension='log', delimiter=',', cli={'path': 'data'}
    )

    assert resource.path == 'data/test.log'
    assert resource.format == 'csv'


# Tests for build_stdin_data / check_cli_commands / run_cli_command ------------
def test_build_stdin_data_returns_none_when_stdin_disabled():
    """No data is built when stdin mode is off, even with a table present."""
    table = etl.wrap([['col1'], ['valor1']])
    assert command.build_stdin_data(table, False, 'utf-8', ',') is None


def test_build_stdin_data_returns_none_when_table_is_none():
    """No data is built when there's no table to serialize, even with stdin on."""
    assert command.build_stdin_data(None, True, 'utf-8', ',') is None


def test_build_stdin_data_serializes_table_as_csv():
    """With stdin on and a table present, the table is serialized as CSV bytes."""
    table = etl.wrap([['col1', 'col2'], ['a', 'b']])
    data = command.build_stdin_data(table, True, 'utf-8', ';')
    assert data == b'col1;col2\r\na;b\r\n'


def test_check_cli_commands_missing_arguments(caplog):
    """No dpetl_transform.cli.arguments logs an error and does nothing."""
    resource = type('Resource', (), {'name': 'test', 'custom': {'dpetl_transform': {'cli': {}}}})()

    command.check_cli_commands(resource, None, False, 'utf-8', ',')

    assert 'Missing required dpetl_transform.cli.arguments' in caplog.text


def test_check_cli_commands_runs_each_argument(monkeypatch):
    """Every argument in the list is passed to run_cli_command, in order."""
    resource = type('Resource', (), {
        'name': 'test',
        'custom': {'dpetl_transform': {'cli': {'arguments': ['cmd1', 'cmd2']}}},
    })()

    calls = []
    monkeypatch.setattr('dpetl.transform.command.run_cli_command', lambda cmd, res, data, **k: calls.append(cmd))

    command.check_cli_commands(resource, None, False, 'utf-8', ',')

    assert calls == ['cmd1', 'cmd2']


def test_check_cli_commands_pipes_stdin_data(monkeypatch):
    """When stdin is enabled, the built data reaches run_cli_command."""
    resource = type('Resource', (), {
        'name': 'test',
        'custom': {'dpetl_transform': {'cli': {'arguments': ['cmd1']}}},
    })()
    table = etl.wrap([['col1'], ['valor1']])

    received = []
    monkeypatch.setattr('dpetl.transform.command.run_cli_command', lambda cmd, res, data, **k: received.append(data))

    command.check_cli_commands(resource, table, True, 'utf-8', ',')

    assert received == [b'col1\r\nvalor1\r\n']


def test_run_cli_command_pipes_data_to_subprocess(monkeypatch):
    """The data argument is forwarded to subprocess.run as input."""
    captured = {}
    def fake_run(cmd, input=None, check=True, **kwargs):
        captured['input'] = input
    monkeypatch.setattr(subprocess, 'run', fake_run)

    command.run_cli_command('cmd', type('Resource', (), {'name': 'test'})(), b'dados')

    assert captured['input'] == b'dados'


def test_run_cli_command_success(caplog):
    """A successful command just logs that it ran."""
    caplog.set_level('DEBUG')

    command.run_cli_command('echo "ok"', type('Resource', (), {'name': 'test'})(), None)

    assert 'Running command:' in caplog.text


def test_run_cli_command_called_process_error(monkeypatch, caplog):
    """A failing command logs the error instead of raising."""
    def fake_run(cmd, check=True, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)
    monkeypatch.setattr(subprocess, 'run', fake_run)

    command.run_cli_command('failing-command', type('Resource', (), {'name': 'test'})(), None)

    assert 'CLI command failed for resource test' in caplog.text


def test_run_cli_command_file_not_found(monkeypatch, caplog):
    """A missing executable logs the error instead of raising."""
    def fake_run(cmd, check=True, **kwargs):
        raise FileNotFoundError("No such file: 'nonexistent'")
    monkeypatch.setattr(subprocess, 'run', fake_run)

    command.run_cli_command('nonexistent', type('Resource', (), {'name': 'test'})(), None)

    assert "CLI command not found for resource test" in caplog.text


# Tests for build_datapackage --------------------------------------------------
@pytest.mark.parametrize(('descriptor_name', 'expected_json'), [
    ('datapackage.yaml', 'datapackage.json'),
    ('existing.yaml', 'existing.json'),
])
def test_build_datapackage(tmp_path, descriptor_name, expected_json):
    """build_datapackage writes a JSON file with the same stem as the descriptor."""
    package = Package(name='test', basepath=str(tmp_path))
    package.metadata_descriptor_path = str(tmp_path / descriptor_name)

    datapackage.build_datapackage(package)

    assert (tmp_path / expected_json).exists()
