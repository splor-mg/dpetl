import typer

from dpetl.helpers import iterator


def transform(ctx: typer.Context):
    """
    Simplified some ETL transform operations.
    """
    iterator.descriptor_iteration(operation='transform', **ctx.obj)
