"""
Unit tests for the iterator module: descriptor discovery and resource iteration.
"""
import pytest
from frictionless import Package

from dpetl.helpers.iterator import descriptor_iteration, resources_iteration


def track_calls(monkeypatch, target):
    """Monkeypatches 'target' (a package-processing function) with a fake that
    records the name of every package it was called with."""
    calls = []
    monkeypatch.setattr(target, lambda package, **k: calls.append(package.name))
    return calls


# Tests for descriptor_iteration -----------------------------------------------
def test_descriptor_iteration_with_explicit_descriptor(monkeypatch, tmp_path):
    """An explicit --descriptor path is loaded and processed directly."""
    desc_file = tmp_path / 'dummy.yaml'
    desc_file.write_text('name: test_package\nresources: []')
    monkeypatch.chdir(tmp_path)

    calls = track_calls(monkeypatch, 'dpetl.extract.extract.extract_package')
    descriptor_iteration(operation='extract', descriptor=[str(desc_file)])

    assert calls == ['test_package']


def test_descriptor_iteration_fallback_datapackage_yaml(monkeypatch, tmp_path):
    """With no --descriptor, it falls back to ./datapackage.yaml."""
    (tmp_path / 'datapackage.yaml').touch()
    monkeypatch.chdir(tmp_path)

    calls = track_calls(monkeypatch, 'dpetl.extract.extract.extract_package')
    monkeypatch.setattr('dpetl.helpers.iterator.Package', lambda path: Package(name='test_pkg'))

    descriptor_iteration(operation='extract')

    assert calls == ['test_pkg']


def test_descriptor_iteration_multiple_descriptors(monkeypatch, tmp_path):
    """Every datapackage.yaml under datapackages/ is processed."""
    for name in ('pkg1', 'pkg2'):
        path = tmp_path / 'datapackages' / name / 'datapackage.yaml'
        path.parent.mkdir(parents=True)
        path.touch()
    monkeypatch.chdir(tmp_path)

    calls = track_calls(monkeypatch, 'dpetl.extract.extract.extract_package')
    monkeypatch.setattr('dpetl.helpers.iterator.Package', lambda path: Package(name='test_pkg'))

    descriptor_iteration(operation='extract')

    assert len(calls) == 2


def test_descriptor_iteration_with_load_operation_and_json_fallback(monkeypatch, tmp_path):
    """operation='load' falls back to ./datapackage.json instead of .yaml."""
    (tmp_path / 'datapackage.json').touch()
    monkeypatch.chdir(tmp_path)

    calls = track_calls(monkeypatch, 'dpetl.load.load.load_package')
    monkeypatch.setattr('dpetl.helpers.iterator.Package', lambda path: Package(name='test_pkg'))

    descriptor_iteration(operation='load')

    assert calls == ['test_pkg']


def test_descriptor_iteration_with_both_yaml_and_json(monkeypatch, tmp_path):
    """When both datapackage.yaml and .json exist, YAML takes priority."""
    (tmp_path / 'datapackage.yaml').touch()
    (tmp_path / 'datapackage.json').touch()
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr('dpetl.helpers.iterator.Package', lambda path: Package(name=f'pkg_from_{path.stem}'))
    calls = track_calls(monkeypatch, 'dpetl.extract.extract.extract_package')

    descriptor_iteration(operation='extract')

    assert calls == ['pkg_from_datapackage']


def test_descriptor_iteration_with_datapackages_folder(monkeypatch, tmp_path):
    """Each subfolder under datapackages/ is loaded from its own datapackage.yaml."""
    for name in ('pkg1', 'pkg2'):
        path = tmp_path / 'datapackages' / name / 'datapackage.yaml'
        path.parent.mkdir(parents=True)
        path.write_text(f'name: {name}')
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr('dpetl.helpers.iterator.Package', lambda path: Package(name=f'pkg_from_{path.parent.name}'))
    calls = track_calls(monkeypatch, 'dpetl.extract.extract.extract_package')

    descriptor_iteration(operation='extract')

    assert sorted(calls) == ['pkg_from_pkg1', 'pkg_from_pkg2']


def test_descriptor_iteration_linktable_receives_all_packages_at_once(monkeypatch, tmp_path):
    """operation='linktable' reads every datapackage.json and dispatches them in a single call."""
    for name in ('pkg1', 'pkg2'):
        path = tmp_path / 'datapackages' / name / 'datapackage.json'
        path.parent.mkdir(parents=True)
        path.touch()
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr('dpetl.helpers.iterator.Package', lambda path: Package(name=f'pkg_from_{path.parent.name}'))
    calls = []
    monkeypatch.setattr(
        'dpetl.linktable.linktable.linktable_packages',
        lambda packages, **k: calls.append(sorted(package.name for package in packages))
    )

    descriptor_iteration(operation='linktable')

    assert calls == [['pkg_from_pkg1', 'pkg_from_pkg2']]


def test_descriptor_iteration_linktable_skips_when_no_descriptor(monkeypatch, tmp_path, caplog):
    """Without any descriptor, linktable logs an error and is not called."""
    monkeypatch.chdir(tmp_path)
    calls = track_calls(monkeypatch, 'dpetl.linktable.linktable.linktable_packages')

    descriptor_iteration(operation='linktable')

    assert calls == []
    assert 'No descriptor found.' in caplog.text


# Tests for resources_iteration - package-level enable/disable -----------------
@pytest.mark.parametrize('custom', [
    {'dpetl_extract': {'enabled': False}},
    {'dpetl_extract': False},
])
def test_resources_iteration_skip_package_when_disabled(monkeypatch, caplog, custom):
    """A disabled package (either shape) is skipped, not processed."""
    caplog.set_level('INFO')
    package = type('Package', (), {'name': 'test_pkg', 'custom': custom})()
    monkeypatch.setattr(
        'dpetl.extract.extract.extract_package',
        lambda *a, **k: (_ for _ in ()).throw(AssertionError('extract_package should not be called'))
    )

    resources_iteration(package, operation='extract')

    assert 'Skipping extract for package test_pkg.' in caplog.text


@pytest.mark.parametrize('custom', [
    {'dpetl_extract': {'enabled': True}},
    {},
])
def test_resources_iteration_process_package_when_enabled(monkeypatch, custom):
    """An enabled package (explicitly, or by having no config at all) is processed."""
    package = type('Package', (), {'name': 'test_pkg', 'custom': custom})()
    calls = track_calls(monkeypatch, 'dpetl.extract.extract.extract_package')

    resources_iteration(package, operation='extract')

    assert calls == ['test_pkg']


# Tests for resources_iteration - operation dispatch ---------------------------
def test_resources_iteration_transform_operation(monkeypatch, fake_package):
    """operation='transform' dispatches to transform_package."""
    calls = track_calls(monkeypatch, 'dpetl.transform.transform.transform_package')

    resources_iteration(fake_package, operation='transform')

    assert calls == [fake_package.name]


def test_resources_iteration_load_operation(monkeypatch, fake_package):
    """operation='load' dispatches to load_package."""
    calls = track_calls(monkeypatch, 'dpetl.load.load.load_package')

    resources_iteration(fake_package, operation='load')

    assert calls == [fake_package.name]


def test_resources_iteration_invalid_operation(fake_package):
    """An unsupported operation raises ValueError instead of silently doing nothing."""
    with pytest.raises(ValueError, match='Unsupported operation'):
        resources_iteration(fake_package, operation='invalid')
