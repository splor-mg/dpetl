import logging
from pathlib import Path
from frictionless import Package

from dpetl.extract import extract
from dpetl.transform import transform
from dpetl.load import load
from dpetl.linktable import linktable

logger = logging.getLogger(__name__)


def resolve_descriptors(operation=None, descriptor=None, **kwargs):
    """
    Resolve which package descriptor(s) an operation should read.
    Returns None when no descriptor is found.
    """
    default = ('datapackage.json' if operation in {'load', 'linktable'}
               else 'datapackage.yaml')

    if descriptor:
        return [Path(path) for path in descriptor]

    if Path(default).exists():
        return [Path(default)]

    if Path('datapackages').is_dir():
        return list(Path('datapackages').glob(f'*/{default}'))

    logger.error('No descriptor found.')
    return None


def descriptor_iteration(**kwargs):
    """
    Iterate on package(s) descriptor(s) and apply a function to each package.
    """
    descriptors = resolve_descriptors(**kwargs)

    if descriptors is None:
        return

    # Linktable combines all packages at once instead of one at a time
    if kwargs.get('operation') == 'linktable':
        packages = [Package(descriptor) for descriptor in descriptors]
        linktable.linktable_packages(packages, **kwargs)
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
