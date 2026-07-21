import typer

from dpetl.helpers import iterator


def extract(
    ctx: typer.Context,

    today_email: bool = typer.Option(
        False,
        '--today-email', '-t',
        help='Extract e-mails received in the same date the command runs.',
    ),

    add_package_name: bool = typer.Option(
        False,
        '--add-package-name', '-a',
        help=(
            'Add the package name to the subject property. '
            'This will search for a subject pattern like '
            '{package_name}_{resource_name} instead of just {resource_name}.'
        ),
    ),
):
    """
    Simplified some ETL extract operations.
    """
    iterator.descriptor_iteration(operation='extract', **ctx.obj,
                                  today_email=today_email,
                                  add_package_name=add_package_name)
