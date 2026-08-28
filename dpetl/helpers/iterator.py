import logging
from pathlib import Path
from frictionless import Package

from dpetl.extract import extract
from dpetl.transform import transform
from dpetl.load import load

logger = logging.getLogger(__name__)


def descriptor_iteration(**kwargs):
    """
    Iterate on package(s) descriptor(s) and apply a function to each package.
    """
    default = ('datapackage.json' if kwargs.get('operation') == 'load'
               else 'datapackage.yaml')

    if kwargs.get('descriptor'):
        descriptors = [Path(descriptor) for descriptor in kwargs.get('descriptor')]

    elif Path(default).exists():
        descriptors = [Path(default)]

    elif Path('datapackages').is_dir():
        descriptors = Path('datapackages').glob(f'*/{default}')

    else:
        logger.error('No descriptor found.')
        return

    for descriptor in descriptors:
        package = Package(descriptor)
        resources_iteration(package, **kwargs)


def resources_iteration(package, **kwargs):
    """
    Iterate on resources from a package descriptor or a package object
    and apply a function to each resource.
    """
    operation = kwargs.get('operation')
    logger = logging.getLogger(f'dpetl.{operation}')

    # Skip the whole operation for the package when disabled
    config = package.custom.get(f'dpetl_{operation}', {})
    enabled = config if isinstance(config, bool) else config.get('enabled', True)

    if not enabled:
        logger.info(
            'Skipping %s for package %s.',
            operation, package.name
        )
        return

    # Extract
    if operation == 'extract':

        logger.info(
            'Extracting package %s.',
            package.name
        )

        extract.extract_package(package, **kwargs)
        return

    # Transform
    elif operation == 'transform':

        logger.info(
            'Transforming package %s.',
            package.name
        )

        transform.transform_package(package, **kwargs)
        return

    # Load
    if operation == 'load':

        logger.info(
            'Loading package %s.',
            package.name
        )

        load.load_package(package, **kwargs)
        return

    raise ValueError(f'Unsupported operation: {operation}')
