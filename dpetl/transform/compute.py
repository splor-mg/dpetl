import logging

import petl as etl
from frictionless import fields

logger = logging.getLogger(__name__)


def apply_compute(schema, field, table):
    """
    Add columns computed by Python expressions to fields that declare a `compute` property.
    Each expression is evaluated per row, with the row's values by field name.
    The columns are added to the schema as strings, right after the field.
    """
    config = field.custom.get('compute')
    if not config:
        return table

    logger.debug('Computing columns %s from field "%s".', list(config), field.name)

    source = list(etl.header(table))
    position = source.index(field.name) + 1
    header = source[:position] + list(config) + source[position:]

    def add_columns(row):
        namespace = dict(zip(source, row))
        values = list(row)
        values[position:position] = [
            eval(expression, {}, namespace)
            for expression in config.values()
        ]
        return values

    names = [schema_field.name for schema_field in schema.fields]
    index = names.index(field.name) + 1
    schema.fields[index:index] = [
        fields.StringField(name=name)
        for name in config
    ]

    # failonerror makes petl raise instead of silently dropping rows
    return etl.rowmap(table, add_columns, header, failonerror=True)
