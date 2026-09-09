"""
Pytest configuration file with shared fixtures for all tests.
"""
import shutil
import pytest
from pathlib import Path
from frictionless import Package, Resource
from typer.testing import CliRunner

import dpetl.helpers.iterator


@pytest.fixture
def runner():
    """Provides a CliRunner instance for testing Typer CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_descriptor_iteration(monkeypatch):
    """
    Monkeypatches descriptor_iteration, capturing all call args for assertions.
    """
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
    monkeypatch.setattr(dpetl.helpers.iterator, 'descriptor_iteration', fake)
    return calls


@pytest.fixture
def fake_package():
    """Minimal Package with one Resource set to email extraction mode."""
    resource = Resource.from_descriptor({
        'name': 'test_resource',
        'path': 'data/test.csv',
        'schema': {'fields': [{'name': 'col1', 'type': 'string'}]},
        'custom': {'dpetl_extract': {'mode': 'email'}}
    })

    if 'custom' in resource.custom:
        resource.custom = resource.custom['custom']

    return Package(resources=[resource], basepath='/tmp')


@pytest.fixture
def dpetl_package(tmp_path):
    """
    Copies the test datapackage fixture to a temp dir and loads it,
    enabling safe read/write operations without affecting the source.
    """
    source = Path(__file__).parent / 'datapackage'
    shutil.copytree(source, tmp_path, dirs_exist_ok=True)
    return Package(str(tmp_path / 'datapackage.yaml'))


@pytest.fixture
def scoped_package():
    """
    Factory that builds a Package with selected resources from another package,
    preserving top-level custom metadata, for isolated resource testing.
    """
    def _scoped(package, *names):
        resources = [package.get_resource(name) for name in names]
        scoped = Package(resources=resources, basepath=package._basepath)
        scoped.custom.update(package.custom)
        return scoped
    return _scoped
