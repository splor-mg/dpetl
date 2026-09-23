"""
Integration tests for the transformation module.
"""
import pytest
import subprocess
from pathlib import Path
import petl as etl
import pandas as pd
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
        lambda resource, **k: cli_calls.append(resource.name)
    )

    package = scoped_package(dpetl_package, 'cli_resource')
    transform.transform_package(package)

    assert cli_calls == ['cli_resource']


def test_transform_package_builds_linktable(dpetl_package, scoped_package, monkeypatch):
    """
    With dpetl_transform.linktable, a fact table and a linktable are written
    inside the package folder, built from the transformed output.
    """
    mock_validation(monkeypatch)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.build_datapackage', lambda *a, **k: None)

    package = scoped_package(dpetl_package, 'fato')
    transform.transform_package(package)

    linktable_dir = Path(package._basepath) / 'data' / 'linktable'

    # Fact table keeps only facts plus the key built from the dimensions
    fact = pd.read_csv(linktable_dir / 'fact_fato.csv.gz', dtype=str)
    assert list(fact.columns) == ['key_fato', 'vlr_empenhado']
    assert fact['vlr_empenhado'].tolist() == ['100', '200', '300']

    # Keys use the renamed and anonymized values, not the raw source ones
    years, agencies = zip(*(key.split('|') for key in fact['key_fato']))
    assert set(years) == {'2024'}
    assert not {'A', 'B'} & set(agencies)

    # Linktable holds the unique dimension rows, comma separated
    table = pd.read_csv(linktable_dir / 'linktable.csv.gz', dtype=str)
    assert list(table.columns) == ['key_fato', 'ano', 'orgao']
    assert len(table) == 2
    assert set(table['key_fato']) == set(fact['key_fato'])

    # Linktable is added to the package with a path relative to it
    resource = package.get_resource('linktable')
    assert resource.path == 'data/linktable/linktable.csv.gz'


def test_transform_package_linktable_is_isolated_per_package(dpetl_package, scoped_package, monkeypatch):
    """Linktable data collected for one package doesn't leak into the next one."""
    mock_validation(monkeypatch)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.write_files', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.update_metadata', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.build_datapackage', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.etl.rename', lambda table, *a: table)
    monkeypatch.setattr('dpetl.transform.transform.anonymize.apply_anonymization', lambda field, table, key: table)
    monkeypatch.setattr(
        'dpetl.transform.transform.linktable.create_fact_tables',
        lambda resource, path: (['dim'], resource.name)
    )

    linktable_calls = []

    def fake_create_linktable(package_dimensions, resource_dfs, *args):
        linktable_calls.append((dict(package_dimensions), list(resource_dfs)))
        return Resource(name='linktable', path='linktable.csv')
    monkeypatch.setattr('dpetl.transform.transform.linktable.create_linktable', fake_create_linktable)

    for _ in range(2):
        transform.transform_package(scoped_package(dpetl_package, 'fato'))

    without_linktable = scoped_package(dpetl_package, 'basic')
    transform.transform_package(without_linktable)

    assert linktable_calls == [({'fato': ['dim']}, ['fato'])] * 2
    assert not without_linktable.has_resource('linktable')


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
        'linktable': False,
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
        'linktable': False,
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


# Tests for check_cli_commands / run_cli_command -------------------------------
def test_check_cli_commands_missing_arguments(caplog):
    """No dpetl_transform.cli.arguments logs an error and does nothing."""
    resource = type('Resource', (), {'name': 'test', 'custom': {'dpetl_transform': {'cli': {}}}})()

    command.check_cli_commands(resource)

    assert 'Missing required dpetl_transform.cli.arguments' in caplog.text


def test_check_cli_commands_runs_each_argument(monkeypatch):
    """Every argument in the list is passed to run_cli_command, in order."""
    resource = type('Resource', (), {
        'name': 'test',
        'custom': {'dpetl_transform': {'cli': {'arguments': ['cmd1', 'cmd2']}}},
    })()

    calls = []
    monkeypatch.setattr('dpetl.transform.command.run_cli_command', lambda cmd, res, **k: calls.append(cmd))

    command.check_cli_commands(resource)

    assert calls == ['cmd1', 'cmd2']


def test_run_cli_command_success(caplog):
    """A successful command just logs that it ran."""
    caplog.set_level('DEBUG')

    command.run_cli_command('echo "ok"', type('Resource', (), {'name': 'test'})())

    assert 'Running command:' in caplog.text


def test_run_cli_command_called_process_error(monkeypatch, caplog):
    """A failing command logs the error instead of raising."""
    def fake_run(cmd, check=True, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)
    monkeypatch.setattr(subprocess, 'run', fake_run)

    command.run_cli_command('failing-command', type('Resource', (), {'name': 'test'})())

    assert 'CLI command failed for resource test' in caplog.text


def test_run_cli_command_file_not_found(monkeypatch, caplog):
    """A missing executable logs the error instead of raising."""
    def fake_run(cmd, check=True, **kwargs):
        raise FileNotFoundError("No such file: 'nonexistent'")
    monkeypatch.setattr(subprocess, 'run', fake_run)

    command.run_cli_command('nonexistent', type('Resource', (), {'name': 'test'})())

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
