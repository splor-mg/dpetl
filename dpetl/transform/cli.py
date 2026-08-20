import typer

from dpetl.helpers import iterator

transform_app = typer.Typer(invoke_without_command=True)


@transform_app.callback()
def transform(ctx: typer.Context):
    """
    Simplified some ETL transform operations.
    """
    if ctx.invoked_subcommand is None:
        iterator.descriptor_iteration(operation='transform', **ctx.obj)


@transform_app.command()
def keygen():
    """
    Generate a secret key for field anonymization.
    """
    import secrets
    key = secrets.token_hex(32)
    typer.echo(f'ANONYMIZE_SECRET_KEY={key}')
