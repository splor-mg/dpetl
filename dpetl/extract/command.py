import logging
import shlex
import subprocess

logger = logging.getLogger(__name__)


def check_cli_commands(resource, **kwargs):
    """
    Execute the command line commands defined for the resource.
    """
    arguments = resource.custom.get('dpetl_extract', {}).get('arguments', [])

    if not arguments:
        logger.error(
            'Missing required dpetl_extract.arguments custom property for resource %s',
            resource.name
        )
        return

    for command in arguments:
        run_cli_command(command, resource, **kwargs)


def run_cli_command(command, resource, **kwargs):
    """
    Execute a single command, logging the error without stopping the others.
    """
    logger.debug(
        'Running command: %s',
        command
    )

    try:
        subprocess.run(shlex.split(command), check=True)

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
