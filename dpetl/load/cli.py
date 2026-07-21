import typer

from dpetl.helpers import iterator


def load(ctx: typer.Context):
    """
    Simplified some ETL load operations.
    """
    iterator.descriptor_iteration(operation='load', **ctx.obj)
