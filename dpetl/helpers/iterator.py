import logging
import tomllib

from frictionless import Package

from dpetl.extract import api, email

logger = logging.getLogger(__name__)

def descriptor_iteration(**kwargs):
    """
    Iterate on package(s) descriptor(s) and apply a function to each package.
    """
    descriptor = kwargs.get('descriptor')
    descriptor_suffix = descriptor.split('.')[-1]
    if descriptor_suffix == 'toml':
        with open(descriptor, "rb") as f:
            descriptors = tomllib.load(f)

        for descriptor in descriptors['datapackages'].values():
            package = Package(descriptor['path'])
            resources_iteration(package, **kwargs)

    elif descriptor_suffix in ['yaml', 'yml', 'json']:
        package = Package(descriptor)
        if not package:
            logger.error(
                'Descriptor does not create a valid package.',
                extra={
                    'package': package.name,
                },
            )
            return
        resources_iteration(package, **kwargs)

def resources_iteration(package, **kwargs):
    """
    Iterate on resources from a package descriptor or a package object
    and apply a function to each resource.
    """

    # TODO: Support all three ETL operations
    for resource in package.resources:
        mode = resource.custom.get('dpetl_extract', {}).get('mode')

        if not mode:
            logger.error(
                ('Missing required dpetl_extract.mode custom property'
                'at the resource level.'),
                extra={
                    'resource': resource.name,
                },
            )
            return

        logger.info(
            'Starting resource extraction.',
            extra={
                'resource': resource.name,
                'mode': mode,
            },
        )

        if mode == 'email':
            email.email_connection(resource, **kwargs)
        elif mode == 'api':
            api.check_multipart_files(resource, **kwargs)
