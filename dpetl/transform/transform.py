import logging
import petl as etl

from dpetl.transform import datapackage
from dpetl.helpers import validate

logger = logging.getLogger('dpetl.transform')


def transform_package(package, **kwargs):
    """
    Transform and export all resources in a datapackage.
    """
    # Validate the datapackage before processing
    validate.validate_datapackage(package, **kwargs)

    rows = []
    errors = []

    for resource in package.resources:

        logger.debug(
            'Transforming resource %s.',
            resource.name,
        )

        # Define output settings
        dpetl = resource.custom.get('dpetl_transform', {})
        parts = (dpetl.get('format') or 'csv.gz').split('.')

        path = dpetl.get('path') or 'data'
        format = parts[0]
        compression = parts[1] if len(parts) > 1 else None
        extension = f'{format}.{compression}' if compression else format
        encoding = dpetl.get('encoding') or 'utf-8'
        delimiter = dpetl.get('delimiter') or ','

        # Rename fields based on target names
        table = resource.to_petl()
        for field in resource.schema.fields:
            target = field.custom.get('target')
            if target:
                table = etl.rename(table, field.name, target)

        # Export the transformed data
        datapackage.write_files(package, resource, path, format, extension, encoding, table, delimiter)

        # Update resource metadata after transformation
        datapackage.update_metadata(resource, path, format, compression, extension, delimiter)

        # Validate the processed resource
        if not validate.check_resource(resource, rows, errors, **kwargs):
            break

    # Display validation results
    validate.validate_resources(rows, errors, **kwargs)

    # Build and save the updated datapackage descriptor
    datapackage.build_datapackage(package)
