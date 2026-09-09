import os
import logging
import petl as etl
from dotenv import load_dotenv, find_dotenv

from dpetl.linktable import create_fact_tables, create_linktable
from dpetl.transform import anonymize, command, datapackage
from dpetl.helpers import validate

logger = logging.getLogger('dpetl.transform')
package_dimensions = {}
resource_dfs = []

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
        if settings['pre_process']:
            table = resource.to_petl()
            for field in resource.schema.fields:
                # Rename fields based on target names
                target = field.custom.get('target')
                if target:
                    table = etl.rename(table, field.name, target)
                    field.name = target

                # Anonymize field
                table = anonymize.apply_anonymization(field, table, secret_key)

        if settings['linktable']:
            dimensions, resource_df = create_fact_tables(resource)

            package_dimensions[resource.name] = dimensions
            resource_dfs.append(resource_df)

            # Export the transformed data
            datapackage.write_files(package, resource, table, **settings)

        # Run an external transformation script
        if settings['cli']:
            command.check_cli_commands(resource, **kwargs)

        # Update resource metadata after transformation
        datapackage.update_metadata(resource, **settings)

        # Validate the processed resource
        if not validate.check_resource(resource, rows, errors, **kwargs):
            break

    if resource_dfs:
        create_linktable(package_dimensions, resource_dfs)

    # Display validation results
    validate.validate_resources(rows, errors, **kwargs)

    # Build and save the updated datapackage descriptor
    datapackage.build_datapackage(package)
