"""
Unit tests for the replace module: replacing parts of a field's values.
"""
from dpetl.transform import replace


def make_field(name, config):
    """
    Builds a lightweight fake field for cases that don't need a real resource.
    """
    return type('Field', (), {
        'name': name,
        'custom': {'replace': config} if config is not None else {},
    })()


def test_apply_replace_without_property_returns_same_table():
    """A field without the replace property is left untouched."""
    table = [['cod'], ['1.2']]
    assert replace.apply_replace(make_field('cod', None), table) is table


def test_apply_replace_removes_characters():
    """A regex replaced by an empty string removes the matched text."""
    table = [['cod', 'valor'], ['1.1.1-2', '1.5'], ['2.3', '2.0']]

    result = replace.apply_replace(make_field('cod', {'[.-]': ''}), table)

    assert list(result) == [
        ('cod', 'valor'),
        ('1112', '1.5'),
        ('23', '2.0'),
    ]


def test_apply_replace_whole_value():
    """Anchored regexes replace only values that match entirely."""
    table = [['situacao'], ['INICIADO'], ['NAO INICIADO']]

    result = replace.apply_replace(make_field('situacao', {'^INICIADO$': 'iniciado'}), table)

    assert list(result) == [('situacao',), ('iniciado',), ('NAO INICIADO',)]


def test_apply_replace_in_order():
    """Replacements are applied in the declared order."""
    table = [['cod'], ['a-b']]

    result = replace.apply_replace(make_field('cod', {'-': '.', r'\.': '_'}), table)

    assert list(result) == [('cod',), ('a_b',)]


def test_apply_replace_keeps_non_strings():
    """Values that are not strings, such as missing values, are kept."""
    table = [['cod'], [None], [12]]

    result = replace.apply_replace(make_field('cod', {'1': ''}), table)

    assert list(result) == [('cod',), (None,), (12,)]
