import logging
import shlex
import subprocess
import petl as etl

logger = logging.getLogger(__name__)


def build_stdin_data(table, stdin, encoding, delimiter, **kwargs):
    """
    Serialize a PETL table to CSV bytes, to pipe into CLI commands via stdin.
    Returns nothing when stdin mode is off or there is no table to serialize.
    """
    if not stdin or table is None:
        return

    source = etl.MemorySource()
    etl.tocsv(table, source, encoding=encoding, delimiter=delimiter)
    return source.getvalue()


def check_cli_commands(resource, table, stdin, encoding, delimiter, **kwargs):
    """
    Execute the command line commands defined for the resource,
    piping the transformed table into each one's stdin when configured.
    """
    arguments = resource.custom.get('dpetl_transform', {}).get('cli', {}).get('arguments', [])

    if not arguments:
        logger.error(
            'Missing required dpetl_transform.cli.arguments custom property for resource %s',
            resource.name
        )
        return

    data = build_stdin_data(table, stdin, encoding, delimiter)

    for command in arguments:
        run_cli_command(command, resource, data, **kwargs)


def run_cli_command(command, resource, data, **kwargs):
    """
    Execute a single command, logging the error without stopping the others.
    """
    logger.debug(
        'Running command: %s',
        command
    )

    try:
        subprocess.run(shlex.split(command), input=data, check=True)

    except subprocess.CalledProcessError as e:
        logger.error(
            'CLI command failed for resource %s: %s',
            resource.name,
            e
        )

    except FileNotFoundError as e:
        logger.error(
            'CLI command not found for resource %s: %s',
            resource.name,
            e
        )
