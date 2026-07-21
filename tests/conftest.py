"""
Pytest configuration file with shared fixtures for all tests.
"""
import pytest
from frictionless import Package, Resource
from typer.testing import CliRunner

import dpetl.helpers.iterator


@pytest.fixture
def runner():
    """
    Provides a CliRunner instance for testing Typer CLI commands.
    Usage: runner.invoke(app, ['command', '--flag'])
    """
    return CliRunner()


@pytest.fixture
def mock_descriptor_iteration(monkeypatch):
    """
    Mocks the descriptor_iteration function to avoid real execution.
    Captures all calls with their arguments for assertion in tests.
    """
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
    monkeypatch.setattr(dpetl.helpers.iterator, 'descriptor_iteration', fake)
    return calls


@pytest.fixture
def fake_package():
    """
    Creates a minimal frictionless Package with one Resource.
    The resource has custom.dpetl_extract.mode = 'email' for testing email extraction.
    """
    resource = Resource.from_descriptor({
        'name': 'test_resource',
        'path': 'data/test.csv',
        'schema': {'fields': [{'name': 'col1', 'type': 'string'}]},
        'custom': {'dpetl_extract': {'mode': 'email'}}
    })

    if 'custom' in resource.custom:
        resource.custom = resource.custom['custom']

    return Package(resources=[resource], basepath='/tmp')
