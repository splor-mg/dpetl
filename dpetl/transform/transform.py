from frictionless import Package
from pathlib import Path
import petl as etl


def transform_resource(descriptor):

    datapackage = Path(descriptor)
    package = Package(datapackage)
    data = datapackage.parent / 'data'

    for resource in package.resources:
        table = resource.to_petl()

        for field in resource.schema.fields:
            target = field.custom.get('target')

            table = etl.rename(table, field.name, target)

        etl.tocsv(table, str(data / f'{resource.name}.csv.gz'), encoding='utf-8')
