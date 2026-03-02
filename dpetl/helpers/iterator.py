import logging

from frictionless import Package

from dpetl.extract import api, email

logger = logging.getLogger(__name__)


def resources_iteration(**kwargs):
    """
    Iterate on resources from a package descriptor or a package object
    and apply a function to each resource.
    """
    descriptor = kwargs.get('descriptor')
    if descriptor:
        package = Package(descriptor)

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
            api.extract_api(resource, **kwargs)
