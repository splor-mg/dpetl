"""
Unit tests for the join module: adding columns from another file to a table.
"""
import json
import logging
import pytest
import petl as etl
from frictionless import Schema

from dpetl.transform import anonymize, join


def make_field(name, config=None):
    """
    Builds a lightweight fake field for cases that don't need a real resource.
    """
    return type('Field', (), {
        'name': name,
        'custom': {'join': config} if config is not None else {},
    })()


def make_schema(*names):
    return Schema.from_descriptor({'fields': [{'name': name, 'type': 'string'} for name in names]})


def write_csv(path, text):
    path.write_text(text, encoding='utf-8')
    return str(path)


def apply(path, table, report, **config):
    field = make_field('uo_cod', {'path': path, **config})
    return join.apply_join(make_schema(*table[0]), field, table, report)


def test_apply_join_without_property_returns_same_table():
    """A field without the join property is left untouched."""
    table = [['uo_cod'], [1]]
    assert join.apply_join(make_schema('uo_cod'), make_field('uo_cod'), table, {}) is table


def test_apply_join_adds_columns_after_the_field(tmp_path):
    """Columns are inserted right after the field, in the declared order."""
    path = write_csv(tmp_path / 'uo.csv', 'uo_cod,uo_sigla,uo_nome\n1,AAA,Alfa\n2,BBB,Beta\n')
    table = [['ano', 'uo_cod', 'valor'], [2024, 2, 10], [2024, 1, 20]]

    result = apply(path, table, {}, columns={'uo_sigla': 'uo_sigla', 'uo_nome': 'uo_nome'})

    assert list(result) == [
        ('ano', 'uo_cod', 'uo_sigla', 'uo_nome', 'valor'),
        (2024, 2, 'BBB', 'Beta', 10),
        (2024, 1, 'AAA', 'Alfa', 20),
    ]


def test_apply_join_by_matches_extra_columns(tmp_path):
    """Rows are matched on the `by` columns as well as on the key."""
    path = write_csv(tmp_path / 'uo.csv', 'ano,uo_cod,uo_sigla\n2023,1,OLD\n2024,1,NEW\n')
    table = [['ano', 'uo_cod'], [2023, 1], [2024, 1]]

    result = apply(path, table, {}, columns={'uo_sigla': 'uo_sigla'}, by={'ano': 'ano'})

    assert list(etl.data(result)) == [(2023, 1, 'OLD'), (2024, 1, 'NEW')]


def test_apply_join_by_with_different_names(tmp_path):
    """
    `by` maps a field of the resource to a column with another name in the file.
    """
    path = write_csv(tmp_path / 'uo.csv', 'ano,uo_cod,uo_sigla\n2023,1,OLD\n2024,1,NEW\n')
    table = [['ano_rp', 'uo_cod'], [2023, 1]]

    result = apply(path, table, {}, columns={'uo_sigla': 'uo_sigla'}, by={'ano_rp': 'ano'})

    assert list(etl.data(result)) == [(2023, 1, 'OLD')]


def test_apply_join_key_with_different_name(tmp_path):
    """`key` names the matching column in the joined file."""
    path = write_csv(tmp_path / 'uo.csv', 'codigo,uo_sigla\n1,AAA\n')
    table = [['uo_cod'], [1]]

    result = apply(path, table, {}, key='codigo', columns={'uo_sigla': 'uo_sigla'})

    assert list(etl.data(result)) == [(1, 'AAA')]


def test_apply_join_unmatched_rows_stay_empty(tmp_path):
    """Rows without a match get empty values."""
    path = write_csv(tmp_path / 'uo.csv', 'uo_cod,uo_sigla\n1,AAA\n')
    table = [['uo_cod'], [1], [9]]

    result = apply(path, table, {}, columns={'uo_sigla': 'uo_sigla'})

    assert list(etl.data(result)) == [(1, 'AAA'), (9, None)]


def test_apply_join_counts_and_logs_missing(tmp_path, caplog):
    """
    Rows without a match are counted per key while the table is read, then logged.
    """
    path = write_csv(tmp_path / 'uo.csv', 'uo_cod,uo_sigla\n1,AAA\n')
    table = [['uo_cod'], [1], [9], [9], [8]]
    report = {}

    result = apply(path, table, report, columns={'uo_sigla': 'uo_sigla'})
    etl.tocsv(result, str(tmp_path / 'out.csv'))
    with caplog.at_level(logging.DEBUG, logger='dpetl.transform.join'):
        join.log_report(report)

    assert report == {('uo_cod', 'without match'): {('9',): 2, ('8',): 1}}
    assert "Join on field \"uo_cod\": 3 rows without match. Examples: [('9',), ('8',)]." in caplog.text


def test_apply_join_empty_value_stays_empty(tmp_path):
    """An empty description in the joined file is kept empty."""
    path = write_csv(tmp_path / 'uo.csv', 'uo_cod,uo_sigla\n1,\n')
    table = [['uo_cod'], [1]]

    result = apply(path, table, {}, columns={'uo_sigla': 'uo_sigla'})

    assert list(etl.data(result)) == [(1, '')]


def test_apply_join_identical_duplicates_are_dropped(tmp_path):
    """Repeated identical rows in the joined file are not a conflict."""
    path = write_csv(tmp_path / 'uo.csv', 'uo_cod,uo_sigla\n1,AAA\n1,AAA\n')
    table = [['uo_cod'], [1]]
    report = {}

    result = apply(path, table, report, columns={'uo_sigla': 'uo_sigla'})

    assert list(etl.data(result)) == [(1, 'AAA')]
    assert report == {}


def test_apply_join_conflicting_duplicates_keep_first_and_log(tmp_path, caplog):
    """
    Different values for the same key keep the first,
    and only rows using that key are reported.
    """
    path = write_csv(tmp_path / 'uo.csv', 'uo_cod,uo_sigla\n1,AAA\n1,ZZZ\n2,BBB\n')
    table = [['uo_cod'], [1], [2]]
    report = {}

    result = apply(path, table, report, columns={'uo_sigla': 'uo_sigla'})
    etl.tocsv(result, str(tmp_path / 'out.csv'))
    with caplog.at_level(logging.DEBUG, logger='dpetl.transform.join'):
        join.log_report(report)

    assert list(etl.data(etl.fromcsv(str(tmp_path / 'out.csv')))) == [('1', 'AAA'), ('2', 'BBB')]
    assert report == {('uo_cod', 'with different values, kept the first'): {('1',): 1}}
    assert 'Join on field "uo_cod": 1 rows with different values, kept the first.' in caplog.text


def test_apply_join_unused_conflicts_are_not_reported(tmp_path):
    """
    A key with different values in the file is not reported when no row uses it.
    """
    path = write_csv(tmp_path / 'uo.csv', 'uo_cod,uo_sigla\n1,AAA\n1,ZZZ\n2,BBB\n')
    table = [['uo_cod'], [2]]
    report = {}

    result = apply(path, table, report, columns={'uo_sigla': 'uo_sigla'})
    etl.tocsv(result, str(tmp_path / 'out.csv'))

    assert report == {}


def test_apply_join_missing_file_exits(tmp_path, caplog):
    """A missing joined file stops the transform with a clear message."""
    table = [['uo_cod'], [1]]

    with pytest.raises(SystemExit):
        apply(str(tmp_path / 'missing.csv'), table, {}, columns={'uo_sigla': 'uo_sigla'})

    assert 'not found' in caplog.text


def test_build_fields_creates_string_fields_for_joined_columns():
    """
    The columns added by a join become string fields, in the declared order.
    """
    field = make_field('uo_cod', {'path': 'uo.csv', 'columns': ['uo_sigla', 'uo_nome']})

    built = join.build_fields(field)

    assert [(item.name, item.type) for item in built] == [('uo_sigla', 'string'), ('uo_nome', 'string')]


def test_build_fields_without_property_is_empty():
    """A field without the join property adds no fields."""
    assert join.build_fields(make_field('uo_cod')) == []


def write_descriptor(tmp_path):
    """Writes a descriptor with two resources, the second one with the joined fields."""
    path = tmp_path / 'datapackage.json'
    path.write_text(json.dumps({'resources': [
        {'name': 'other', 'path': 'other.csv', 'schema': {'fields': [
            {'name': 'uo_nome', 'type': 'integer'},
        ]}},
        {'name': 'uo', 'path': 'uo.csv', 'schema': {'fields': [
            {'name': 'uo_nome', 'type': 'string', 'title': 'Nome', 'target': 'other_name'},
        ]}},
    ]}))
    return str(path)


def test_build_fields_copies_fields_from_descriptor(tmp_path):
    """With a descriptor, the complete field is copied from the given resource, with the new name."""
    descriptor = {'path': write_descriptor(tmp_path), 'resource': 'uo'}
    field = make_field('uo_cod', {
        'path': 'uo.csv',
        'columns': {'uo_fin_nome': 'uo_nome'},
        'descriptor': descriptor,
    })

    built = join.build_fields(field)

    assert [(item.name, item.type, item.title) for item in built] == [('uo_fin_nome', 'string', 'Nome')]
    assert built[0].custom == {'target': 'other_name'}


def test_build_fields_uses_first_resource_of_descriptor(tmp_path):
    """Without a resource name, the first resource of the descriptor is used."""
    descriptor = {'path': write_descriptor(tmp_path)}
    field = make_field('uo_cod', {
        'path': 'other.csv',
        'columns': {'uo_nome': 'uo_nome'},
        'descriptor': descriptor,
    })

    built = join.build_fields(field)

    assert [(item.name, item.type) for item in built] == [('uo_nome', 'integer')]


def test_apply_join_anonymizes_column_from_descriptor(tmp_path):
    """The added field keeps the descriptor's `anonymize`, so the transform can apply it."""
    path = write_csv(tmp_path / 'uo.csv', 'uo_cod,uo_nome\n1,Alfa\n2,Beta\n')
    descriptor_path = tmp_path / 'datapackage.json'
    descriptor_path.write_text(json.dumps({'resources': [
        {'name': 'uo', 'path': 'uo.csv', 'schema': {'fields': [
            {'name': 'uo_nome', 'type': 'string',
             'anonymize': {'method': '[RESTRICTED]', 'filter': 'int(uo_cod) == 2'}},
        ]}},
    ]}))
    field = make_field('uo_cod', {
        'path': path,
        'columns': {'uo_nome': 'uo_nome'},
        'descriptor': {'path': str(descriptor_path)},
    })

    schema = make_schema('uo_cod')
    result = join.apply_join(schema, field, [['uo_cod'], [1], [2]], {})
    result = anonymize.apply_anonymization(schema.fields[1], result, None)

    assert list(etl.data(result)) == [(1, 'Alfa'), (2, 'RESTRICTED')]


def test_apply_join_adds_fields_to_schema_after_the_field(tmp_path):
    """The fields of the added columns go into the schema right after the field."""
    path = write_csv(tmp_path / 'uo.csv', 'uo_cod,uo_sigla\n1,AAA\n')
    schema = make_schema('ano', 'uo_cod', 'valor')
    field = make_field('uo_cod', {'path': path, 'columns': {'uo_sigla': 'uo_sigla'}})

    join.apply_join(schema, field, [['ano', 'uo_cod', 'valor'], [2024, 1, 10]], {})

    assert [item.name for item in schema.fields] == ['ano', 'uo_cod', 'uo_sigla', 'valor']
