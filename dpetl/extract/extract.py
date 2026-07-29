import logging

from dpetl.extract import api, email
from dpetl.helpers import validate

logger = logging.getLogger(__name__)


def extract_package(package, **kwargs):
    """
    Extract data from all resources in a datapackage based on their configured mode.
    """
    rows = []
    errors = []

    for resource in package.resources:
        # Get extraction mode from resource custom metadata
        mode = resource.custom.get('dpetl_extract', {}).get('mode')

        if not mode:
            logger.error(
                'Missing required dpetl_extract.mode custom property for resource %s',
                resource.name
            )
            return

        logger.debug(
            'Extracting resource %s using mode %s.',
            resource.name,
            mode
        )

        # Run the extraction based on the configured mode
        if mode == 'email':
            email.email_connection(resource, **kwargs)
        elif mode == 'api':
            api.check_multipart_files(resource, **kwargs)

        # Check if the extracted data is valid
        if not validate.check_resource(resource, rows, errors, **kwargs):
            break

    # Display validation results and exit if there were errors
    validate.validate_resources(rows, errors, **kwargs)
