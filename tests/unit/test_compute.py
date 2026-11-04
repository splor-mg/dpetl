"""
Unit tests for the compute module: adding columns computed from other fields.
"""
from frictionless import Schema

from dpetl.transform import compute


def make_field(name, config):
    """
    Builds a lightweight fake field for cases that don't need a real resource.
    """
    return type('Field', (), {
        'name': name,
        'custom': {'compute': config} if config is not None else {},
    })()


def make_schema(*names):
    return Schema.from_descriptor({'fields': [{'name': name, 'type': 'string'} for name in names]})


def test_apply_compute_without_property_returns_same_table():
    """A field without the compute property is left untouched."""
    table = [['item_cod'], ['1']]
    assert compute.apply_compute(make_schema('item_cod'), make_field('item_cod', None), table) is table


def test_apply_compute_adds_columns_after_the_field():
    """Computed columns are inserted right after the field, in the declared order."""
    schema = make_schema('elemento_cod', 'item_cod', 'valor')
    field = make_field('item_cod', {
        'elemento_item_cod': 'elemento_cod + item_cod.zfill(2)',
        'elemento_int': 'int(elemento_cod)',
    })
    table = [['elemento_cod', 'item_cod', 'valor'], ['91', '3', '10'], ['1', '12', '20']]

    result = compute.apply_compute(schema, field, table)

    assert list(result) == [
        ('elemento_cod', 'item_cod', 'elemento_item_cod', 'elemento_int', 'valor'),
        ('91', '3', '9103', 91, '10'),
        ('1', '12', '112', 1, '20'),
    ]


def test_apply_compute_adds_string_fields_to_schema():
    """Computed columns are added to the schema as strings, right after the field."""
    schema = make_schema('elemento_cod', 'item_cod', 'valor')
    field = make_field('item_cod', {'elemento_item_cod': 'elemento_cod + item_cod'})

    compute.apply_compute(schema, field, [['elemento_cod', 'item_cod', 'valor']])

    assert [schema_field.name for schema_field in schema.fields] == [
        'elemento_cod', 'item_cod', 'elemento_item_cod', 'valor',
    ]
    assert schema.get_field('elemento_item_cod').type == 'string'
