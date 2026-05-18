import petl as etl
from pathlib import Path
from datetime import datetime


def write_files(package, resource, path, format, extension, encoding, table):

    output = Path(package._basepath) / path / f'{resource.name}.{extension}'
    output.parent.mkdir(parents=True, exist_ok=True)

    if format in ['csv', 'txt']:
        etl.tocsv(table, str(output), encoding=encoding)

    elif format == 'xlsx':
        etl.toxlsx(table, str(output))

    else:
        raise ValueError(f'Unsupported format: {format}')


def update_metadata(resource, path, format, compression, extension):

    schema = resource.schema.fields

    resource.path = f'{path}/{resource.name}.{extension}'
    resource.scheme = 'file'
    resource.format = format
    resource.compression = compression

    for index, field in enumerate(schema):
        target = field.custom.get('target')

        if target:
            schema[index] = field.to_copy(name=target)

    for field in schema:
        field.custom.pop('target', None)

    [resource.custom.pop(key, None) for key in ['dpetl_extract', 'dpetl_transform']]
    resource.extrapaths = None
    resource.infer(stats=True)


def build_datapackage(package, datapackage_format):

    package.custom['updated_at'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    descriptor = Path(package.metadata_descriptor_path).stem
    output = Path(package._basepath) / f'{descriptor}.{datapackage_format}'

    if datapackage_format in ['yaml', 'yml']:
        package.to_yaml(output)

    else:
        output.write_text(package.to_json())
