import petl as etl

from .datapackage import write_files, update_metadata, build_datapackage


def transform_resource(package):

    for resource in package.resources:

        dpetl = resource.custom.get('dpetl_transform', {})
        parts = (dpetl.get('format') or 'csv.gz').split('.')

        path = dpetl.get('path') or 'data'
        format = parts[0]
        compression = (parts[1] if len(parts) > 1 else None)
        extension = f'{format}.{compression}' if compression else format
        encoding = dpetl.get('encoding') or 'utf-8'

        table = resource.to_petl()

        for field in resource.schema.fields:
            target = field.custom.get('target')

            table = etl.rename(table, field.name, target)

        write_files(package, resource, path, format, extension, encoding, table)

        update_metadata(resource, path, format, compression, extension)

    datapackage_format = package.custom.get('dpetl_transform', {}).get('datapackage_format', 'json')
    build_datapackage(package, datapackage_format)
