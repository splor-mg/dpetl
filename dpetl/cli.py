import logging
import typer
from typing import Annotated, Optional
from importlib.metadata import version

from .extract.cli import extract
from .transform.cli import transform
from .load.cli import load


app = typer.Typer(name='etl', help='ETL Command Line Interface',
                  pretty_exceptions_show_locals=False)

app.command()(extract)
app.command()(transform)
app.command()(load)


def setup_logging(verbose: bool, quiet: bool):
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    handlers = [logging.StreamHandler()]

    if verbose:
        handlers.append(logging.FileHandler('dpetl.debug.log', encoding='utf-8'))

    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)-5.5s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers,
    )


def version_callback(value: bool):
    if value:
        typer.echo(f"dpetl {version('dpetl')}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,

    descriptor: Annotated[
        Optional[list[str]],
        typer.Option('--descriptor', '-d',
                     help='Path to datapackage descriptor.',
                     show_default='datapackage.yaml (extract/transform) '
                                  '/ datapackage.json (load) '
                                  'or datapackages/*/'
)
    ] = None,

    no_validate: Annotated[
        bool,
        typer.Option('--no-validate', '-nv',
                     help='Skip datapackage validation.'),
    ] = False,

    no_stop: Annotated[
        bool,
        typer.Option('--no-stop', '-ns',
                     help='Do not stop the process if validation fails.'),
    ] = False,

    validate_before: Annotated[
        bool,
        typer.Option('--validate-before', '-vb',
                     help='Validate datapackage before processing.'),
    ] = False,


    verbose: Annotated[
        bool,
        typer.Option('--verbose',
                     help='Enable debug logging.'),
    ] = False,

    quiet: Annotated[
        bool,
        typer.Option('--quiet', '-q',
                     help='Show only warnings and errors.'),
    ] = False,

    version: Annotated[
        bool,
        typer.Option('--version', '-v',
                     callback=version_callback, is_eager=True,
                     help='Show the application version and exit.'),
    ] = False,
):
    setup_logging(verbose, quiet)

    if verbose and quiet:
        raise typer.BadParameter(
            "'--verbose' cannot be used together with '--quiet'."
        )

    if validate_before and no_validate:
        raise typer.BadParameter(
            "'--validate-before' cannot be used together with '--no-validate'."
        )

    if validate_before and ctx.invoked_subcommand == 'extract':
        raise typer.BadParameter(
             "'--validate-before' is not supported for the 'extract' command."
        )

    ctx.obj = {
        'descriptor': descriptor,
        'no_validate': no_validate,
        'no_stop': no_stop,
        'validate_before': validate_before,
    }
