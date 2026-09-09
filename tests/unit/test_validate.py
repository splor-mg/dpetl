"""
Unit tests for the validate module: resource and datapackage validation.
"""
import pytest

from dpetl.helpers import validate


def make_report(valid, errors=None):
    """A minimal stand-in for a frictionless validation Report."""
    task = type('Task', (), {
        'valid': valid,
        'name': 'res',
        'type': 'file',
        'place': 'path',
        'errors': errors or [],
    })()
    return type('Report', (), {'tasks': [task]})()


def make_error(type_='schema-error', message='Invalid'):
    return type('Error', (), {'type': type_, 'message': message})()


# Tests for check_resource -----------------------------------------------------
def test_check_resource_valid(monkeypatch):
    """A valid report returns True and records a VALID row."""
    monkeypatch.setattr('dpetl.helpers.validate.validate', lambda *a, **k: make_report(valid=True))
    rows, errors = [], []

    result = validate.check_resource(type('Resource', (), {})(), rows, errors)

    assert result is True
    assert rows[0][3] == 'VALID'
    assert len(errors) == 0


def test_check_resource_validation_fails(monkeypatch):
    """An invalid report returns False and records an INVALID row plus its errors."""
    monkeypatch.setattr('dpetl.helpers.validate.validate', lambda *a, **k: make_report(valid=False, errors=[make_error()]))
    rows, errors = [], []

    result = validate.check_resource(type('Resource', (), {})(), rows, errors, no_stop=False)

    assert result is False
    assert rows[0][3] == 'INVALID'
    assert len(errors) == 1


def test_check_resource_skip_validation(monkeypatch):
    """no_validate=True returns True without ever calling frictionless' validate()."""
    def fail(*a, **k):
        raise AssertionError('validate should not be called')
    monkeypatch.setattr('dpetl.helpers.validate.validate', fail)
    rows, errors = [], []

    result = validate.check_resource(type('Resource', (), {})(), rows, errors, no_validate=True)

    assert result is True
    assert rows == []
    assert errors == []


# Tests for validate_resources -------------------------------------------------
def test_validate_resources_with_errors(capsys):
    """Errors are printed and sys.exit(1) is called."""
    rows = [['res', 'file', 'path', 'INVALID']]
    errors = [type('Task', (), {'name': 'res', 'errors': [make_error()]})()]

    with pytest.raises(SystemExit):
        validate.validate_resources(rows, errors)

    captured = capsys.readouterr()
    assert 'Errors in res' in captured.out
    assert 'schema-error' in captured.out


def test_validate_resources_no_errors(capsys):
    """With no errors, only the results table is printed, no error section."""
    validate.validate_resources([['res', 'file', 'path', 'VALID']], [])

    captured = capsys.readouterr()
    assert 'Errors' not in captured.out
    assert 'VALID' in captured.out


def test_validate_resources_with_stop_false(capsys):
    """no_stop=True prints errors but doesn't call sys.exit."""
    rows = [['res', 'file', 'path', 'INVALID']]
    errors = [type('Task', (), {'name': 'res', 'errors': [make_error()]})()]

    validate.validate_resources(rows, errors, no_stop=True)

    assert 'Errors in res' in capsys.readouterr().out


# Tests for validate_datapackage -----------------------------------------------
def test_validate_datapackage_calls_check_for_each_resource(monkeypatch, fake_package):
    """Every resource in the package is passed through check_resource."""
    calls = []

    def mock_check_resource(resource, rows, errors, **kwargs):
        calls.append(resource.name)
        rows.append([resource.name, 'file', 'path', 'VALID'])
        return True

    monkeypatch.setattr('dpetl.helpers.validate.check_resource', mock_check_resource)
    monkeypatch.setattr('dpetl.helpers.validate.validate_resources', lambda *a, **k: None)

    validate.validate_datapackage(fake_package, validate_before=True, no_validate=False)

    assert len(calls) == len(fake_package.resources)


@pytest.mark.parametrize('kwargs', [
    {'no_validate': True, 'validate_before': True},
    {'no_validate': False, 'validate_before': False},
])
def test_validate_datapackage_skip(monkeypatch, fake_package, kwargs):
    """no_validate=True, or validate_before=False, both skip check_resource entirely."""
    def fail(*a, **k):
        raise AssertionError('check_resource should not be called')
    monkeypatch.setattr('dpetl.helpers.validate.check_resource', fail)

    validate.validate_datapackage(fake_package, **kwargs)


def test_validate_datapackage_with_validation_failure(monkeypatch, fake_package):
    """A failing resource is still recorded, without validate_datapackage itself raising."""
    calls = []

    def mock_check_resource(resource, rows, errors, **kwargs):
        calls.append(resource.name)
        rows.append([resource.name, 'file', 'path', 'INVALID'])
        errors.append(type('Task', (), {'name': resource.name, 'errors': [make_error()]})())
        return False

    monkeypatch.setattr('dpetl.helpers.validate.check_resource', mock_check_resource)
    monkeypatch.setattr('dpetl.helpers.validate.validate_resources', lambda *a, **k: None)

    validate.validate_datapackage(fake_package, validate_before=True, no_validate=False, no_stop=True)

    assert calls == [fake_package.resources[0].name]
