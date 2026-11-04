import typer
from typing import Optional

from dpetl.helpers import iterator


def linktable(
    ctx: typer.Context,

    name: Optional[str] = typer.Option(
        None,
        '--name', '-n',
        help=(
            'Name of the linktable data package, saved to datapackages/<name>. '
            'Required across data packages. With a single -d it defaults '
            'to <package>_linktable.'
        ),
    ),
):
    """
    Build fact tables and a linktable as a new data package.
    """
    iterator.descriptor_iteration(
        operation='linktable', **ctx.obj,
        name=name,
    )
