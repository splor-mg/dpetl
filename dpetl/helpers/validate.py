import sys
from frictionless import validate
from tabulate import tabulate


def check_resource(resource, rows, errors, **kwargs):
    """
    Validates a resource and adds its result to the validation report.
    If validation fails, processing stops unless no_stop is enabled.
    """
    no_validate = kwargs.get('no_validate')
    no_stop = kwargs.get('no_stop')

    # Skip validation if '--no-validate' flag is set
    if no_validate:
        return True

    # Validate the resource
    report = validate(resource, skip_errors=['blank-row'])
    task = report.tasks[0]

    # Add validation result to the summary
    rows.append([task.name, task.type, task.place,
                 'VALID' if task.valid else 'INVALID'])

    # Record validation failures
    if not task.valid:
        errors.append(task)
        if not no_stop:
            return False

    return True


def validate_datapackage(package, **kwargs):
    """
    Validate all resources of a datapackage, before any processing.
    """
    # Skip validation when not requested
    if kwargs.get('no_validate') or not kwargs.get('validate_before'):
        return

    rows = []
    errors = []

    # Validate each resource in the package
    for resource in package.resources:
        if not check_resource(resource, rows, errors, **kwargs):
            break

    validate_resources(rows, errors, **kwargs)


def validate_resources(rows, errors, **kwargs):
    """
    Displays validation results and detected errors.
    If validation fails, execution stops unless no_stop is enabled.
    """
    # Show validation summary
    if rows:
        print(tabulate(rows, headers=['name', 'type', 'path', 'status'],
                       tablefmt='simple_grid'))

    # Show validation errors grouped by type
    for task in errors:
        print(f'\nErrors in {task.name}:')
        grouped = {}
        for error in task.errors:
            grouped.setdefault(error.type, []).append(error)

        for error_type, error_msg in grouped.items():
            print(f'\n[{error_type}] {len(error_msg)} occurrence(s) — example:')
            print(f' - {error_msg[0].message}')

    # Stop execution if errors were found
    if errors and not kwargs.get('no_stop'):
        sys.exit(1)
