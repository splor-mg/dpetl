"""
Unit tests for the validate module: resource and datapackage validation.
"""
import pytest

from dpetl.helpers import validate


# Tests for check_resource -----------------------------------------------------
def test_check_resource_valid(monkeypatch):
    """
    Test that check_resource returns True and adds a VALID row when validation succeeds.
    """
    # Mock the frictionless validate function to return a valid report
    class MockReport:
        class Task:
            valid = True
            name = 'res'
            type = 'file'
            place = 'path'
            errors = []
        tasks = [Task()]

    def mock_validate(*args, **kwargs):
        return MockReport()

    monkeypatch.setattr('dpetl.helpers.validate.validate', mock_validate)

    resource = type('Resource', (), {})()
    rows = []
    errors = []

    result = validate.check_resource(resource, rows, errors)

    assert result is True
    assert rows[0][3] == 'VALID'
    assert len(errors) == 0


def test_check_resource_validation_fails(monkeypatch):
    """
    Test that check_resource returns False and adds an INVALID row when validation fails.
    """
    # Mock the frictionless validate function to return an invalid report
    class Error:
        def __init__(self, type, message):
            self.type = type
            self.message = message

    class Task:
        valid = False
        name = 'res'
        type = 'file'
        place = 'path'
        errors = [Error('schema-error', 'Invalid')]

    class MockReport:
        tasks = [Task()]

    def mock_validate(*args, **kwargs):
        return MockReport()

    monkeypatch.setattr('dpetl.helpers.validate.validate', mock_validate)

    resource = type('Resource', (), {})()
    rows = []
    errors = []

    result = validate.check_resource(resource, rows, errors, no_stop=False)

    assert result is False
    assert rows[0][3] == 'INVALID'
    assert len(errors) == 1


def test_check_resource_skip_validation(monkeypatch):
    """
    Test that check_resource returns True without calling validate when no_validate=True.
    """
    # Mock validate to fail if called
    def mock_validate(*args, **kwargs):
        raise AssertionError("validate should not be called")

    monkeypatch.setattr('dpetl.helpers.validate.validate', mock_validate)

    resource = type('Resource', (), {})()
    rows = []
    errors = []

    result = validate.check_resource(resource, rows, errors, no_validate=True)

    assert result is True
    assert len(rows) == 0
    assert len(errors) == 0


# Tests for validate_resources -------------------------------------------------
def test_validate_resources_with_errors(capsys):
    """
    Test that validate_resources prints errors and calls sys.exit(1) when there are errors.
    """
    # Create a mock task with errors
    task = type('Task', (), {
        'name': 'res',
        'errors': [type('Error', (), {'type': 'schema-error', 'message': 'Invalid'})]
    })()

    rows = [['res', 'file', 'path', 'INVALID']]
    errors = [task]

    with pytest.raises(SystemExit):
        validate.validate_resources(rows, errors)

    captured = capsys.readouterr()
    assert 'Errors in res' in captured.out
    assert 'schema-error' in captured.out


def test_validate_resources_no_errors(capsys):
    """
    Test that validate_resources prints nothing when there are no errors.
    """
    rows = [['res', 'file', 'path', 'VALID']]
    errors = []

    validate.validate_resources(rows, errors)

    captured = capsys.readouterr()
    assert 'Errors' not in captured.out
    assert 'VALID' in captured.out


def test_validate_resources_with_stop_false(capsys):
    """
    Test that validate_resources does NOT call sys.exit when no_stop=True, even with errors.
    """
    task = type('Task', (), {
        'name': 'res',
        'errors': [type('Error', (), {'type': 'schema-error', 'message': 'Invalid'})]
    })()

    rows = [['res', 'file', 'path', 'INVALID']]
    errors = [task]

    # Should not raise SystemExit
    validate.validate_resources(rows, errors, no_stop=True)

    captured = capsys.readouterr()
    assert 'Errors in res' in captured.out


# Tests for validate_datapackage -----------------------------------------------
def test_validate_datapackage_calls_check_for_each_resource(monkeypatch, fake_package):
    """
    Test that validate_datapackage calls check_resource for each resource in the package.
    """
    calls = []

    def mock_check_resource(resource, rows, errors, **kwargs):
        calls.append(resource.name)
        rows.append([resource.name, 'file', 'path', 'VALID'])
        return True

    def mock_validate_resources(rows, errors, **kwargs):
        pass

    monkeypatch.setattr('dpetl.helpers.validate.check_resource', mock_check_resource)
    monkeypatch.setattr('dpetl.helpers.validate.validate_resources', mock_validate_resources)

    from dpetl.helpers import validate
    validate.validate_datapackage(fake_package, validate_before=True, no_validate=False)

    assert len(calls) == len(fake_package.resources)


def test_validate_datapackage_skip_when_no_validate(monkeypatch, fake_package):
    """
    Test that validate_datapackage returns early when no_validate=True.
    """
    # Mock check_resource to fail if called
    def mock_check_resource(*args, **kwargs):
        raise AssertionError("check_resource should not be called")

    monkeypatch.setattr('dpetl.helpers.validate.check_resource', mock_check_resource)

    from dpetl.helpers import validate
    # Should return without calling check_resource
    validate.validate_datapackage(fake_package, no_validate=True, validate_before=True)


def test_validate_datapackage_skip_when_no_validate_before(monkeypatch, fake_package):
    """
    Test that validate_datapackage returns early when validate_before=False.
    """
    # Mock check_resource to fail if called
    def mock_check_resource(*args, **kwargs):
        raise AssertionError('check_resource should not be called')

    monkeypatch.setattr('dpetl.helpers.validate.check_resource', mock_check_resource)

    from dpetl.helpers import validate
    # Should return without calling check_resource
    validate.validate_datapackage(fake_package, validate_before=False, no_validate=False)


def test_validate_datapackage_with_validation_failure(monkeypatch, fake_package, capsys):
    """
    Test that validate_datapackage handles validation failure correctly.
    This covers the remaining uncovered line (validate.py:42).
    """
    calls = []

    def mock_check_resource(resource, rows, errors, **kwargs):
        calls.append(resource.name)
        rows.append([resource.name, 'file', 'path', 'INVALID'])
        # Simulate a validation error
        task = type('Task', (), {
            'name': resource.name,
            'errors': [type('Error', (), {'type': 'schema-error', 'message': 'Invalid'})]
        })()
        errors.append(task)
        return False  # validation fails

    def mock_validate_resources(rows, errors, **kwargs):
        # This should be called with the errors
        pass

    monkeypatch.setattr('dpetl.helpers.validate.check_resource', mock_check_resource)
    monkeypatch.setattr('dpetl.helpers.validate.validate_resources', mock_validate_resources)

    from dpetl.helpers import validate

    # Should not raise SystemExit because validate_resources is mocked
    validate.validate_datapackage(fake_package, validate_before=True, no_validate=False, no_stop=True)

    # Verify that check_resource was called
    assert len(calls) == 1
    assert calls[0] == fake_package.resources[0].name
