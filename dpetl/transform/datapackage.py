import petl as etl
from pathlib import Path
from datetime import datetime


def write_files(package, resource, path, format, extension, encoding, table):
    """
    Export a PETL table to the configured output format.
    """
    # Ensure the output directory exists
    output = Path(package._basepath) / path / f'{resource.name}.{extension}'
    output.parent.mkdir(parents=True, exist_ok=True)

    # Write file based on selected format
    if format in ['csv', 'txt']:
        etl.tocsv(table, str(output), encoding=encoding)

    elif format == 'xlsx':
        etl.toxlsx(table, str(output))

    else:
        raise ValueError(f'Unsupported format: {format}')


def update_metadata(resource, path, format, compression, extension):
    """
    Update resource metadata after transformation to match the generated output file.
    """
    schema = resource.schema.fields

    # Update file-related resource properties
    resource.path = f'{path}/{resource.name}.{extension}'
    resource.scheme = 'file'
    resource.format = format
    resource.compression = compression

    for index, field in enumerate(schema):
        target = field.custom.get('target')

        if target:
            schema[index] = field.to_copy(name=target)

    # Remove target metadata from all fields
    for field in schema:
        field.custom.pop('target', None)

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
