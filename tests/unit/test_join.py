"""
Unit tests for the join module: adding columns from another file to a table.
"""
import logging
import pytest
import petl as etl

from dpetl.transform import join


def make_field(name, config=None):
    """
    Builds a lightweight fake field for cases that don't need a real resource.
    """
    return type('Field', (), {
        'name': name,
        'custom': {'join': config} if config is not None else {},
    })()


def write_csv(path, text):
    path.write_text(text, encoding='utf-8')
    return str(path)


def apply(path, table, report, **config):
    field = make_field('uo_cod', {'path': path, **config})
    return join.apply_join(field, table, report)


def test_apply_join_without_property_returns_same_table():
    """A field without the join property is left untouched."""
    table = [['uo_cod'], [1]]
    assert join.apply_join(make_field('uo_cod'), table, {}) is table


def test_apply_join_adds_columns_after_the_field(tmp_path):
    """Columns are inserted right after the field, in the declared order."""
    path = write_csv(tmp_path / 'uo.csv', 'uo_cod,uo_sigla,uo_nome\n1,AAA,Alfa\n2,BBB,Beta\n')
    table = [['ano', 'uo_cod', 'valor'], [2024, 2, 10], [2024, 1, 20]]

    result = apply(path, table, {}, columns=['uo_sigla', 'uo_nome'])

    assert list(result) == [
        ('ano', 'uo_cod', 'uo_sigla', 'uo_nome', 'valor'),
        (2024, 2, 'BBB', 'Beta', 10),
        (2024, 1, 'AAA', 'Alfa', 20),
    ]


def test_apply_join_by_matches_extra_columns(tmp_path):
    """Rows are matched on the `by` columns as well as on the key."""
    path = write_csv(tmp_path / 'uo.csv', 'ano,uo_cod,uo_sigla\n2023,1,OLD\n2024,1,NEW\n')
    table = [['ano', 'uo_cod'], [2023, 1], [2024, 1]]

    result = apply(path, table, {}, columns=['uo_sigla'], by={'ano': 'ano'})

    assert list(etl.data(result)) == [(2023, 1, 'OLD'), (2024, 1, 'NEW')]


def test_apply_join_by_with_different_names(tmp_path):
    """
    `by` maps a field of the resource to a column with another name in the file.
    """
    path = write_csv(tmp_path / 'uo.csv', 'ano,uo_cod,uo_sigla\n2023,1,OLD\n2024,1,NEW\n')
    table = [['ano_rp', 'uo_cod'], [2023, 1]]

    result = apply(path, table, {}, columns=['uo_sigla'], by={'ano_rp': 'ano'})

    assert list(etl.data(result)) == [(2023, 1, 'OLD')]


def test_apply_join_key_with_different_name(tmp_path):
    """`key` names the matching column in the joined file."""
    path = write_csv(tmp_path / 'uo.csv', 'codigo,uo_sigla\n1,AAA\n')
    table = [['uo_cod'], [1]]

    result = apply(path, table, {}, key='codigo', columns=['uo_sigla'])

    assert list(etl.data(result)) == [(1, 'AAA')]


def test_apply_join_unmatched_rows_stay_empty(tmp_path):
    """Rows without a match get empty values."""
    path = write_csv(tmp_path / 'uo.csv', 'uo_cod,uo_sigla\n1,AAA\n')
    table = [['uo_cod'], [1], [9]]

    result = apply(path, table, {}, columns=['uo_sigla'])

    assert list(etl.data(result)) == [(1, 'AAA'), (9, None)]


def test_apply_join_counts_and_logs_missing(tmp_path, caplog):
    """
    Rows without a match are counted per key while the table is read, then logged.
    """
    path = write_csv(tmp_path / 'uo.csv', 'uo_cod,uo_sigla\n1,AAA\n')
    table = [['uo_cod'], [1], [9], [9], [8]]
    report = {}

    etl.tocsv(apply(path, table, report, columns=['uo_sigla']), str(tmp_path / 'out.csv'))
    with caplog.at_level(logging.DEBUG, logger='dpetl.transform.join'):
        join.log_report(report)

    assert report == {('uo_cod', 'without match'): {('9',): 2, ('8',): 1}}
    assert "Join on field \"uo_cod\": 3 rows without match. Examples: [('9',), ('8',)]." in caplog.text


def test_apply_join_empty_value_stays_empty(tmp_path):
    """An empty description in the joined file is kept empty."""
    path = write_csv(tmp_path / 'uo.csv', 'uo_cod,uo_sigla\n1,\n')
    table = [['uo_cod'], [1]]

    result = apply(path, table, {}, columns=['uo_sigla'])

    assert list(etl.data(result)) == [(1, '')]


def test_apply_join_identical_duplicates_are_dropped(tmp_path):
    """Repeated identical rows in the joined file are not a conflict."""
    path = write_csv(tmp_path / 'uo.csv', 'uo_cod,uo_sigla\n1,AAA\n1,AAA\n')
    table = [['uo_cod'], [1]]
    report = {}

    result = apply(path, table, report, columns=['uo_sigla'])

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

    etl.tocsv(apply(path, table, report, columns=['uo_sigla']), str(tmp_path / 'out.csv'))
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

    etl.tocsv(apply(path, table, report, columns=['uo_sigla']), str(tmp_path / 'out.csv'))

    assert report == {}


def test_apply_join_missing_file_exits(tmp_path, caplog):
    """A missing joined file stops the transform with a clear message."""
    table = [['uo_cod'], [1]]

    with pytest.raises(SystemExit):
        apply(str(tmp_path / 'missing.csv'), table, {}, columns=['uo_sigla'])

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
