"""
Unit tests for the iterator module: descriptor discovery and resource iteration.
"""
import pytest
from frictionless import Package


# Tests for descriptor_iteration -----------------------------------------------
def test_descriptor_iteration_with_explicit_descriptor(monkeypatch, tmp_path):
    """
    Test that descriptor_iteration processes a single explicit descriptor file.
    """
    # Create a minimal datapackage descriptor
    descriptor_content = """
name: test_package
resources:
  - name: res
    path: data.csv
    schema:
      fields:
        - name: col1
          type: string
"""
    desc_file = tmp_path / 'dummy.yaml'
    desc_file.write_text(descriptor_content)
    monkeypatch.chdir(tmp_path)

    # Mock the extract function to capture calls
    calls = []

    def fake_extract_package(package, **kwargs):
        calls.append(package.name)

    monkeypatch.setattr('dpetl.extract.extract.extract_package', fake_extract_package)

    from dpetl.helpers.iterator import descriptor_iteration
    descriptor_iteration(operation='extract', descriptor=[str(desc_file)])

    assert calls == ['test_package']


def test_descriptor_iteration_fallback_datapackage_yaml(monkeypatch, tmp_path):
    """
    Test that descriptor_iteration falls back to datapackage.yaml when no descriptor is provided.
    """
    (tmp_path / 'datapackage.yaml').touch()
    monkeypatch.chdir(tmp_path)

    calls = []

    def fake_extract_package(package, **kwargs):
        calls.append(package.name)

    monkeypatch.setattr('dpetl.extract.extract.extract_package', fake_extract_package)
    fake_package = Package(name='test_pkg')
    monkeypatch.setattr('dpetl.helpers.iterator.Package', lambda path: fake_package)

    from dpetl.helpers.iterator import descriptor_iteration
    descriptor_iteration(operation='extract')

    assert calls == ['test_pkg']


def test_descriptor_iteration_multiple_descriptors(monkeypatch, tmp_path):
    """
    Test that descriptor_iteration processes all descriptors found in the datapackages/ folder.
    """
    # Create two package descriptors in the datapackages/ folder
    (tmp_path / 'datapackages' / 'pkg1' / 'datapackage.yaml').parent.mkdir(parents=True)
    (tmp_path / 'datapackages' / 'pkg1' / 'datapackage.yaml').touch()
    (tmp_path / 'datapackages' / 'pkg2' / 'datapackage.yaml').parent.mkdir(parents=True)
    (tmp_path / 'datapackages' / 'pkg2' / 'datapackage.yaml').touch()
    monkeypatch.chdir(tmp_path)

    calls = []

    def fake_extract_package(package, **kwargs):
        calls.append(package.name)

    monkeypatch.setattr('dpetl.extract.extract.extract_package', fake_extract_package)
    fake_package = Package(name='test_pkg')
    monkeypatch.setattr('dpetl.helpers.iterator.Package', lambda path: fake_package)

    from dpetl.helpers.iterator import descriptor_iteration
    descriptor_iteration(operation='extract')

    assert len(calls) == 2


def test_descriptor_iteration_with_load_operation_and_json_fallback(monkeypatch, tmp_path):
    """
    Test that descriptor_iteration with operation='load' falls back to datapackage.json.
    """
    (tmp_path / 'datapackage.json').touch()
    monkeypatch.chdir(tmp_path)

    calls = []

    def fake_load_package(package, **kwargs):
        calls.append(package.name)

    monkeypatch.setattr('dpetl.load.load.load_package', fake_load_package)
    fake_package = Package(name='test_pkg')
    monkeypatch.setattr('dpetl.helpers.iterator.Package', lambda path: fake_package)

    from dpetl.helpers.iterator import descriptor_iteration
    descriptor_iteration(operation='load')

    assert calls == ['test_pkg']


def test_descriptor_iteration_with_both_yaml_and_json(monkeypatch, tmp_path):
    """
    Test that when both datapackage.yaml and datapackage.json exist, YAML takes priority.
    """
    (tmp_path / 'datapackage.yaml').touch()
    (tmp_path / 'datapackage.json').touch()
    monkeypatch.chdir(tmp_path)

    def fake_package_loader(path):
        return Package(name=f'pkg_from_{path.stem}')

    monkeypatch.setattr('dpetl.helpers.iterator.Package', fake_package_loader)

    calls = []

    def fake_extract_package(package, **kwargs):
        calls.append(package.name)

    monkeypatch.setattr('dpetl.extract.extract.extract_package', fake_extract_package)

    from dpetl.helpers.iterator import descriptor_iteration
    descriptor_iteration(operation='extract')

    # Should load from datapackage.yaml, not datapackage.json
    assert calls == ['pkg_from_datapackage']


def test_descriptor_iteration_with_datapackages_folder(monkeypatch, tmp_path):
    """
    Test that descriptor_iteration processes multiple packages found in the datapackages/ folder.
    """
    # Create two package descriptors with actual content
    (tmp_path / 'datapackages' / 'pkg1' / 'datapackage.yaml').parent.mkdir(parents=True)
    (tmp_path / 'datapackages' / 'pkg1' / 'datapackage.yaml').write_text('name: pkg1')
    (tmp_path / 'datapackages' / 'pkg2' / 'datapackage.yaml').parent.mkdir(parents=True)
    (tmp_path / 'datapackages' / 'pkg2' / 'datapackage.yaml').write_text('name: pkg2')
    monkeypatch.chdir(tmp_path)

    def fake_package_loader(path):
        return Package(name=f'pkg_from_{path.parent.name}')

    monkeypatch.setattr('dpetl.helpers.iterator.Package', fake_package_loader)

    calls = []

    def fake_extract_package(package, **kwargs):
        calls.append(package.name)

    monkeypatch.setattr('dpetl.extract.extract.extract_package', fake_extract_package)

    from dpetl.helpers.iterator import descriptor_iteration
    descriptor_iteration(operation='extract')

    assert sorted(calls) == ['pkg_from_pkg1', 'pkg_from_pkg2']


# Tests for resources_iteration ------------------------------------------------
def test_resources_iteration_transform_operation(monkeypatch, fake_package):
    """
    Test that resources_iteration dispatches to transform_package when operation='transform'.
    """
    calls = []

    def fake_transform_package(package, **kwargs):
        calls.append(('transform', package.name))

    monkeypatch.setattr('dpetl.transform.transform.transform_package', fake_transform_package)

    from dpetl.helpers.iterator import resources_iteration
    resources_iteration(fake_package, operation='transform')

    assert calls == [('transform', fake_package.name)]


def test_resources_iteration_load_operation(monkeypatch, fake_package):
    """
    Test that resources_iteration dispatches to load_package when operation='load'.
    """
    calls = []

    def fake_load_package(package, **kwargs):
        calls.append(('load', package.name))

    monkeypatch.setattr('dpetl.load.load.load_package', fake_load_package)

    from dpetl.helpers.iterator import resources_iteration
    resources_iteration(fake_package, operation='load')

    assert calls == [('load', fake_package.name)]


def test_resources_iteration_invalid_operation(fake_package):
    """
    Test that resources_iteration raises ValueError for unsupported operations.
    """
    from dpetl.helpers.iterator import resources_iteration

    with pytest.raises(ValueError, match='Unsupported operation'):
        resources_iteration(fake_package, operation='invalid')
