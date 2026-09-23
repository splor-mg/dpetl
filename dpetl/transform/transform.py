import os
import logging
import petl as etl
from dotenv import load_dotenv, find_dotenv
from pathlib import Path

from dpetl.transform import linktable
from dpetl.transform import anonymize, command, datapackage
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

    # Define path for Linktable if nedded later
    basepath = Path(package._basepath)
    resource_path = Path(package.resources[0].path)
    linktable_path = basepath / resource_path.parent / 'linktable'

    rows = []
    errors = []

    # Linktable dimensions and data collected per package
    package_dimensions = {}
    resource_dfs = []

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

            # Export the transformed data
            datapackage.write_files(package, resource, table, **settings)

        # Run an external transformation script
        if settings['cli']:
            command.check_cli_commands(resource, **kwargs)

        # Update resource metadata after transformation
        datapackage.update_metadata(resource, **settings)

        # Build fact table from the transformed output
        if settings['linktable']:
            dimensions, resource_df = linktable.create_fact_tables(resource, linktable_path)

            package_dimensions[resource.name] = dimensions
            resource_dfs.append(resource_df)

        # Validate the processed resource
        if not validate.check_resource(resource, rows, errors, **kwargs):
            break

    if resource_dfs:
        linktable_resource = linktable.create_linktable(package_dimensions, resource_dfs, linktable_path, basepath)
        package.resources.append(linktable_resource)

    # Display validation results
    validate.validate_resources(rows, errors, **kwargs)

    # Build and save the updated datapackage descriptor
    datapackage.build_datapackage(package)
