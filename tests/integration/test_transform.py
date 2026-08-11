"""
Integration tests for the transformation module.
Tests: write_files, update_metadata, build_datapackage, and transform_package.
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


# Tests for write_files  -------------------------------------------------------
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

    datapackage.write_files(FakePackage(), FakeResource(), 'data', format, extension, 'utf-8', table, ',')

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
