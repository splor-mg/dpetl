import petl as etl
from pathlib import Path
from datetime import datetime
from frictionless import Dialect, Resource

from dpetl.transform import anonymize


def get_output_settings(resource):
    """
    Extract output settings from the resource custom metadata.
    """
    dpetl = resource.custom.get('dpetl_transform', {})
    cli = dpetl.get('cli') or {}
    parts = (dpetl.get('format') or 'csv.gz').split('.')
    format = parts[0]
    compression = parts[1] if len(parts) > 1 else None

    return {
        'path': dpetl.get('path') or 'data',
        'format': format,
        'compression': compression,
        'extension': f'{format}.{compression}' if compression else format,
        'encoding': dpetl.get('encoding') or 'utf-8',
        'delimiter': dpetl.get('delimiter') or ',',
        'cli': dpetl.get('cli'),
        'pre_process': cli.get('pre_process', True),
    }


def write_files(package, resource, table, path, format, extension, encoding, delimiter, **kwargs):
    """
    Export a PETL table to the configured output format.
    """
    # Ensure the output directory exists
    output = Path(package._basepath) / path / f'{resource.name}.{extension}'
    output.parent.mkdir(parents=True, exist_ok=True)

    # Write file based on selected format
    if format in ['csv', 'txt']:
        etl.tocsv(table, str(output), encoding=encoding, delimiter=delimiter)

    elif format == 'xlsx':
        etl.toxlsx(table, str(output))

    else:
        raise ValueError(f'Unsupported format: {format}')


def update_metadata(resource, path, format, compression, extension, delimiter, cli, **kwargs):
    """
    Update resource metadata after transformation to match the generated output file.
    """
    if cli:
        basepath = resource.package._basepath
        directory = Path(basepath) / (cli.get('path') or path)

        for output in directory.iterdir():
            if output.is_file() and output.stem.lower() == resource.name:
                break

        relative_path = str(output.relative_to(basepath))

        def infer(**options):
            inferred = Resource(path=relative_path, basepath=basepath, **options)
            inferred.infer(stats=True)
            return inferred

        inferred = infer()
        if inferred.type != 'table':
            inferred = infer(format=format)

        resource.path = inferred.path
        resource.scheme = inferred.scheme
        resource.format = inferred.format
        resource.compression = inferred.compression
        resource.encoding = inferred.encoding
        resource.dialect = inferred.dialect
        resource.schema = inferred.schema
        resource.stats = inferred.stats

    else:
        # Update file-related resource properties
        resource.path = f'{path}/{resource.name}.{extension}'
        resource.scheme = 'file'
        resource.format = format
        resource.compression = compression
        resource.dialect = Dialect.from_descriptor({'csv': {'delimiter': delimiter}})

    # Update field properties
    schema = resource.schema.fields
    for index, field in enumerate(schema):
        schema[index] = field.to_copy(
            constraints=anonymize.build_constraints(field),
        )

    # Remove custom property from all fields
    for field in schema:
        field.custom.pop('target', None)
        field.custom.pop('anonymize', None)

    # Clear extrapaths and infer schema from the output file
    resource.extrapaths = None
    resource.infer(stats=True)


def build_datapackage(package):
    """
    Build and save the updated datapackage descriptor as JSON.
    """
    # Add timestamp to package custom metadata
    package.custom['updated_at'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    # Save the updated descriptor as JSON
    descriptor = Path(package.metadata_descriptor_path).stem
    output = Path(package._basepath) / f'{descriptor}.json'
    output.write_text(package.to_json())

    # Update the descriptor path to the generated JSON file
    package.metadata_descriptor_path = str(output)
