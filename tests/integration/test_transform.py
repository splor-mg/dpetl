"""
Integration tests for the transformation module.
"""
import pytest
import csv
import petl as etl
from frictionless import Package, Resource

from dpetl.transform import datapackage, transform


# Helpers ----------------------------------------------------------------------
class FakePackage:
    def __init__(self, basepath='/tmp'):
        self._basepath = basepath


class FakeResource:
    name = 'test'


def mock_validation(monkeypatch):
    """Apply common mocks to skip validation during transform tests."""
    monkeypatch.setattr('dpetl.transform.transform.validate.validate_datapackage', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.validate.check_resource', lambda *a, **k: True)
    monkeypatch.setattr('dpetl.transform.transform.validate.validate_resources', lambda *a, **k: None)


# Tests for transform_package --------------------------------------------------
def test_transform_package(fake_package, monkeypatch):
    """
    Verify that transform_package orchestrates the transformation steps in order:
    1. validate_datapackage
    2. write_files (for each resource)
    3. update_metadata (for each resource)
    4. validate resources
    5. build_datapackage
    """
    calls = []

    mock_validation(monkeypatch)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.write_files', lambda *a, **k: calls.append('write'))
    monkeypatch.setattr('dpetl.transform.transform.datapackage.update_metadata', lambda *a, **k: calls.append('update'))
    monkeypatch.setattr('dpetl.transform.transform.datapackage.build_datapackage', lambda *a, **k: calls.append('build'))

    transform.transform_package(fake_package)

    assert calls == ['write', 'update', 'build']


def test_transform_package_with_target(tmp_path, monkeypatch):
    """Test that transform_package renames fields based on target property."""
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    csv_path = data_dir / 'test.csv'
    with open(csv_path, 'w', encoding='utf-8') as f:
        f.write('col1\nvalor1\n')

    resource = Resource.from_descriptor({
        'name': 'test',
        'path': 'data/test.csv',
        'schema': {
            'fields': [
                {'name': 'col1', 'type': 'string'}
            ]
        },
        'custom': {'dpetl_transform': {'format': 'csv'}}
    }, basepath=str(tmp_path))

    resource.schema.fields[0].custom['target'] = 'nova_col1'

    package = Package(resources=[resource], basepath=str(tmp_path))

    mock_validation(monkeypatch)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.build_datapackage', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.validate.check_resource', lambda *a, **k: True)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.update_metadata', lambda *a, **k: None)

    rename_calls = []
    def fake_rename(table, old_name, new_name):
        rename_calls.append((old_name, new_name))
        return table
    monkeypatch.setattr('dpetl.transform.transform.etl.rename', fake_rename)

    transform.transform_package(package)

    assert rename_calls == [('col1', 'nova_col1')]


def test_transform_package_with_anonymize(tmp_path, monkeypatch, caplog):
    """Test that transform_package applies anonymization to resources."""
    import logging
    caplog.set_level(logging.DEBUG)

    monkeypatch.setenv('ANONYMIZE_SECRET_KEY', '0123456789abcdef0123456789abcdef')

    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    csv_path = data_dir / 'test.csv'
    with open(csv_path, 'w', encoding='utf-8') as f:
        f.write('col1\nvalor1\nvalor2\n')

    resource = Resource.from_descriptor({
        'name': 'test',
        'path': 'data/test.csv',
        'schema': {
            'fields': [
                {'name': 'col1', 'type': 'string'}
            ]
        },
        'custom': {'dpetl_transform': {'format': 'csv'}}
    }, basepath=str(tmp_path))

    # Force custom anonymize on the field
    resource.schema.fields[0].custom = {'anonymize': {'method': 'sha256'}}

    package = Package(resources=[resource], basepath=str(tmp_path))

    mock_validation(monkeypatch)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.build_datapackage', lambda *a, **k: None)

    transform.transform_package(package)

    assert 'Anonymizing field' in caplog.text


def test_transform_package_validation_failure(tmp_path, monkeypatch):
    """Test that transform_package breaks the loop when validation fails."""
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    csv_path = data_dir / 'test.csv'
    with open(csv_path, 'w', encoding='utf-8') as f:
        f.write('col1\nvalor1\n')

    resource = Resource.from_descriptor({
        'name': 'test',
        'path': 'data/test.csv',
        'schema': {
            'fields': [
                {'name': 'col1', 'type': 'string'}
            ]
        },
        'custom': {'dpetl_transform': {'format': 'csv'}}
    }, basepath=str(tmp_path))

    package = Package(resources=[resource], basepath=str(tmp_path))

    mock_validation(monkeypatch)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.build_datapackage', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.validate.check_resource', lambda *a, **k: False)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.update_metadata', lambda *a, **k: None)

    write_calls = []
    monkeypatch.setattr('dpetl.transform.transform.datapackage.write_files', lambda *a, **k: write_calls.append('write'))

    transform.transform_package(package)

    assert write_calls == ['write']


# Tests for get_output_settings ------------------------------------------------
def test_get_output_settings():
    """Test extracting output settings from resource custom metadata."""
    # Full configuration
    resource = type('Resource', (), {
        'custom': {
            'dpetl_transform': {
                'path': 'custom_data',
                'format': 'csv.gz',
                'encoding': 'latin1',
                'delimiter': ';'
            }
        }
    })()
    settings = datapackage.get_output_settings(resource)
    assert settings['path'] == 'custom_data'
    assert settings['format'] == 'csv'
    assert settings['compression'] == 'gz'
    assert settings['extension'] == 'csv.gz'
    assert settings['encoding'] == 'latin1'
    assert settings['delimiter'] == ';'

    # Defaults
    resource = type('Resource', (), {'custom': {}})()
    settings = datapackage.get_output_settings(resource)
    assert settings['path'] == 'data'
    assert settings['format'] == 'csv'
    assert settings['compression'] == 'gz'
    assert settings['extension'] == 'csv.gz'
    assert settings['encoding'] == 'utf-8'
    assert settings['delimiter'] == ','


# Tests for write_files --------------------------------------------------------
@pytest.mark.parametrize(('format', 'extension'), [
    ('csv', 'csv'),
    ('txt', 'txt'),
    ('xlsx', 'xlsx'),
])
def test_write_files_formats(tmp_path, format, extension):
    """Test writing files in different formats (CSV, TXT, XLSX)."""
    if format == 'xlsx':
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            pytest.skip('openpyxl not installed, skipping XLSX test')

    package = FakePackage(basepath=str(tmp_path))
    resource = FakeResource()
    table = etl.wrap([['col1', 'col2'], ['a', 'b']])

    datapackage.write_files(package, resource, table, 'data', format, extension, 'utf-8', ',')

    assert (tmp_path / 'data' / f'test.{extension}').exists()


def test_write_files_unsupported_format():
    """Test write_files raises ValueError for unsupported format."""
    package = FakePackage()
    resource = FakeResource()
    table = etl.wrap([['col1', 'col2'], ['a', 'b']])

    with pytest.raises(ValueError, match='Unsupported format'):
        datapackage.write_files(
            package, resource, table,
            'data', 'unsupported', 'unsupported', 'utf-8', ','
        )


# Tests for update_metadata ----------------------------------------------------
@pytest.mark.parametrize('compression, expected_path', [
    (None, 'processed/test.csv'),
    ('gz', 'processed/test.csv.gz'),
])
def test_update_metadata(tmp_path, monkeypatch, compression, expected_path):
    """Test that update_metadata updates path, fields, and compression."""
    basepath = tmp_path
    data_dir = basepath / 'data'
    data_dir.mkdir()
    csv_path = data_dir / 'data.csv'
    with open(csv_path, 'w', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['col1'])
        writer.writerow(['valor1'])

    resource = Resource.from_descriptor({
        'name': 'test',
        'path': 'data/data.csv',
        'schema': {'fields': [{'name': 'col1', 'type': 'string'}]}
    }, basepath=str(basepath))

    resource.schema.fields[0].custom = {'target': 'nova_col1'}
    monkeypatch.setattr(resource, 'infer', lambda *args, **kwargs: None)

    extension = 'csv.gz' if compression else 'csv'
    datapackage.update_metadata(resource, 'processed', 'csv', compression, extension, ',')

    assert resource.path == expected_path
    assert resource.schema.fields[0].name == 'nova_col1'
    if compression:
        assert resource.compression == compression
        assert resource.format == 'csv'


def test_update_metadata_with_anonymize(tmp_path, monkeypatch):
    """Test that update_metadata adds constraints from anonymize config."""
    basepath = tmp_path
    data_dir = basepath / 'data'
    data_dir.mkdir()
    csv_path = data_dir / 'data.csv'
    with open(csv_path, 'w', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['col1'])
        writer.writerow(['valor1'])

    resource = Resource.from_descriptor({
        'name': 'test',
        'path': 'data/data.csv',
        'schema': {
            'fields': [
                {
                    'name': 'col1',
                    'type': 'string'
                }
            ]
        }
    }, basepath=str(basepath))

    resource.schema.fields[0].custom = {'anonymize': {'method': 'sha256'}}
    monkeypatch.setattr(resource, 'infer', lambda *args, **kwargs: None)

    datapackage.update_metadata(resource, 'processed', 'csv', None, 'csv', ',')

    constraints = resource.schema.fields[0].constraints
    assert 'pattern' in constraints
    assert constraints['pattern'] == '^[0-9a-f]{16}$'


# Tests for build_datapackage --------------------------------------------------
@pytest.mark.parametrize(('descriptor_name', 'expected_json'), [
    ('datapackage.yaml', 'datapackage.json'),
    ('existing.yaml', 'existing.json'),
])
def test_build_datapackage(tmp_path, descriptor_name, expected_json):
    """
    Test that build_datapackage creates a JSON file with the same stem as the descriptor.
    """
    package = Package(name='test', basepath=str(tmp_path))
    package.metadata_descriptor_path = str(tmp_path / descriptor_name)

    datapackage.build_datapackage(package)

    assert (tmp_path / expected_json).exists()
