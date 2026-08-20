"""
Integration tests for the transformation module.
"""
import csv
import pytest
from frictionless import Package, Resource

from dpetl.transform import datapackage, transform


# Tests for transform_package (main orchestrator) ------------------------------
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

    monkeypatch.setattr('dpetl.transform.transform.validate.validate_datapackage', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.write_files', lambda *a, **k: calls.append('write'))
    monkeypatch.setattr('dpetl.transform.transform.datapackage.update_metadata', lambda *a, **k: calls.append('update'))
    monkeypatch.setattr('dpetl.transform.transform.validate.check_resource', lambda *a, **k: True)
    monkeypatch.setattr('dpetl.transform.transform.validate.validate_resources', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.build_datapackage', lambda *a, **k: calls.append('build'))

    transform.transform_package(fake_package)

    assert calls == ['write', 'update', 'build']


def test_transform_package_with_anonymize(tmp_path, monkeypatch, caplog):
    """
    Test that transform_package applies anonymization to resources.
    """
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

    monkeypatch.setattr('dpetl.transform.transform.validate.validate_datapackage', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.validate.validate_resources', lambda *a, **k: None)
    monkeypatch.setattr('dpetl.transform.transform.datapackage.build_datapackage', lambda *a, **k: None)

    transform.transform_package(package)

    assert 'Anonymizing field' in caplog.text


# Tests for get_output_settings ------------------------------------------------
def test_get_output_settings():
    """
    Test extracting output settings from resource custom metadata.
    """
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

    resource2 = type('Resource', (), {'custom': {}})()
    settings2 = datapackage.get_output_settings(resource2)
    assert settings2['path'] == 'data'
    assert settings2['format'] == 'csv'
    assert settings2['compression'] == 'gz'
    assert settings2['extension'] == 'csv.gz'
    assert settings2['encoding'] == 'utf-8'
    assert settings2['delimiter'] == ','


# Tests for write_files --------------------------------------------------------
@pytest.mark.parametrize(('format', 'extension'), [
    ('csv', 'csv'),
    ('txt', 'txt'),
    ('xlsx', 'xlsx'),
])
def test_write_files_formats(tmp_path, format, extension):
    """
    Test writing files in different formats (CSV, TXT, XLSX).
    XLSX is skipped if openpyxl is not installed.
    """
    if format == 'xlsx':
        try:
            import openpyxl
        except ImportError:
            pytest.skip('openpyxl not installed, skipping XLSX test')

    class FakePackage:
        _basepath = str(tmp_path)

    class FakeResource:
        name = 'test'

    table = [['col1', 'col2'], ['a', 'b']]

    datapackage.write_files(FakePackage(), FakeResource(), table, 'data', format, extension, 'utf-8', ',')

    assert (tmp_path / 'data' / f'test.{extension}').exists()


# Tests for update_metadata ----------------------------------------------------
def test_update_metadata(tmp_path, monkeypatch):
    """
    Test that update_metadata updates path and renames fields based on custom.target.
    """
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

    datapackage.update_metadata(resource, 'processed', 'csv', None, 'csv', ',')

    assert resource.path == 'processed/test.csv'
    assert resource.schema.fields[0].name == 'nova_col1'


def test_update_metadata_with_compression(tmp_path, monkeypatch):
    """
    Test update_metadata with compression format (e.g., csv.gz).
    """
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

    monkeypatch.setattr(resource, 'infer', lambda *args, **kwargs: None)

    datapackage.update_metadata(resource, 'processed', 'csv', 'gz', 'csv.gz', ',')

    assert resource.compression == 'gz'
    assert resource.format == 'csv'
    assert resource.path == 'processed/test.csv.gz'


def test_update_metadata_with_anonymize(tmp_path, monkeypatch):
    """
    Test that update_metadata adds constraints from anonymize config.
    """
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

    # Force custom anonymize on the field
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
