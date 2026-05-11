from frictionless import validate
from tabulate import tabulate


def validate_datapackage(datapackage):
    report = validate(datapackage, skip_errors=['blank-row'])

    rows = []
    for task in report.tasks:
        rows.append([task.name, task.type, task.place,
                        'VALID' if task.valid else 'INVALID'])

    print(tabulate(rows, headers=['name', 'type', 'path', 'status'],
                    tablefmt='simple_grid'))

    for task in report.tasks:
        if not task.valid:
            print(f'\nErrors in {task.name}:')

            for error in task.errors:
                print(f' - {error.message}')
