import typer

from dpetl.helpers import iterator


def linktable(ctx: typer.Context):
    """
    Build a linktable across data packages and load it to GitHub.
    """
    iterator.descriptor_iteration(operation='linktable', **ctx.obj)
