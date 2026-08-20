import os
import logging
import petl as etl
from dotenv import load_dotenv, find_dotenv

from dpetl.transform import datapackage, anonymize
from dpetl.helpers import validate

logger = logging.getLogger('dpetl.transform')


def transform_package(package, **kwargs):
    """
    Transform and export all resources in a datapackage.
    """
    # Validate the datapackage before processing
    validate.validate_datapackage(package, **kwargs)

    # Load the anonymization secret key if present
    load_dotenv(find_dotenv(usecwd=True))
    secret_key = os.environ.get('ANONYMIZE_SECRET_KEY')

    rows = []
    errors = []

    for resource in package.resources:

        logger.debug(
            'Transforming resource %s.',
            resource.name,
        )

        # Define output settings
        settings = datapackage.get_output_settings(resource)

        # Apply transformation functions to a field
        table = resource.to_petl()
        for field in resource.schema.fields:
            # Anonymize field
            table = anonymize.apply_anonymization(field, table, secret_key)

            # Rename fields based on target names
            target = field.custom.get('target')
            if target:
                table = etl.rename(table, field.name, target)

        # Export the transformed data
        datapackage.write_files(package, resource, table, **settings)

        # Update resource metadata after transformation
        datapackage.update_metadata(resource, **settings)

        # Validate the processed resource
        if not validate.check_resource(resource, rows, errors, **kwargs):
            break

    # Display validation results
    validate.validate_resources(rows, errors, **kwargs)

    # Build and save the updated datapackage descriptor
    datapackage.build_datapackage(package)
