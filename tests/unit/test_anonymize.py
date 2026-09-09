"""
Unit tests for the anonymize module: field masking, hashing, and schema constraints.
"""
import pytest
import logging
import re
import petl as etl

from dpetl.transform import anonymize


def make_field(anonymize_config=None, missing_values=None, constraints=None):
    """Builds a lightweight fake field for cases that don't need a real resource."""
    return type('Field', (), {
        'name': 'col1',
        'missing_values': missing_values or [],
        'custom': {'anonymize': anonymize_config} if anonymize_config is not None else {},
        'constraints': constraints or {},
    })()


def field_by_name(resource, name):
    return next(f for f in resource.schema.fields if f.name == name)


# Tests for _apply_mask --------------------------------------------------------
def test_apply_mask_basic():
    """Mask with separators."""
    assert anonymize._apply_mask('[###-###]', '123456') == '123-456'
    assert anonymize._apply_mask('[***-***]', '123456') == '***-***'
    assert anonymize._apply_mask('[##* - ##*]', '123456') == '12* - 45*'


def test_apply_mask_multiple_variants():
    """Mask with multiple variants selected by digit count."""
    pattern = '[###-####|#####-###]'
    assert anonymize._apply_mask(pattern, '1234567') == '123-4567'
    assert anonymize._apply_mask(pattern, '12345678') == '12345-678'
    assert anonymize._apply_mask(pattern, '12') == '12'


def test_apply_mask_literal_fixed():
    """A fixed literal (no # or *) is returned as-is, ignoring the value."""
    assert anonymize._apply_mask('[abc]', 'anything') == 'abc'


def test_apply_mask_character_masking():
    """# preserves a character, * masks it."""
    assert anonymize._apply_mask('[#*****]', 'Maria') == 'M****'
    assert anonymize._apply_mask('[*****]', 'João') == '****'


def test_apply_mask_cpf_cnpj():
    """Real-world CPF/CNPJ masks."""
    cpf = '12345678909'
    cnpj = '12345678000199'
    assert anonymize._apply_mask('[###.###.###-##]', cpf) == '123.456.789-09'
    assert anonymize._apply_mask('[***.###.###-**]', cpf) == '***.456.789-**'
    assert anonymize._apply_mask('[##.###.###/####-##]', cnpj) == '12.345.678/0001-99'
    assert anonymize._apply_mask('[**.###.###/****-##]', cnpj) == '**.345.678/****-99'


# Tests for apply_anonymization - real resource data ---------------------------
def test_apply_anonymization_sha256(dpetl_package):
    """sha256 produces a 16-char hex token, different from the original value."""
    resource = dpetl_package.get_resource('anonymized')
    field = field_by_name(resource, 'col1')
    table = resource.to_petl()

    data = list(anonymize.apply_anonymization(field, table, None))

    values = [row[data[0].index('col1')] for row in data[1:]]
    assert values != ['value1', 'value2', 'value3']
    assert all(len(v) == 16 for v in values)


def test_apply_anonymization_aes_siv(dpetl_package):
    """aes_siv produces a deterministic 32-char hex token when given the same key."""
    resource = dpetl_package.get_resource('anonymized')
    field = field_by_name(resource, 'col2')
    table = resource.to_petl()
    secret_key = '0123456789abcdef0123456789abcdef'

    first = list(anonymize.apply_anonymization(field, table, secret_key))
    second = list(anonymize.apply_anonymization(field, table, secret_key))

    col_index = first[0].index('col2')
    assert len(first[1][col_index]) == 32
    assert first[1][col_index] == second[1][col_index]


def test_apply_anonymization_mask_method(dpetl_package):
    """A mask pattern (e.g. '[###-###]') is used directly as the anonymize method."""
    resource = dpetl_package.get_resource('anonymized')
    field = field_by_name(resource, 'col3')
    table = resource.to_petl()

    data = list(anonymize.apply_anonymization(field, table, None))

    col_index = data[0].index('col3')
    assert data[1][col_index] == '123-456'


def test_apply_anonymization_with_annotation(dpetl_package):
    """Annotation labels are prefixed onto the token based on the value's digit count."""
    resource = dpetl_package.get_resource('anonymized')
    field = field_by_name(resource, 'col4')
    table = resource.to_petl()

    data = list(anonymize.apply_anonymization(field, table, None))

    col_index = data[0].index('col4')
    assert data[1][col_index].startswith('short:')   # '1'   -> 1 digit
    assert data[2][col_index].startswith('long:')    # '12'  -> 2 digits
    assert not data[3][col_index].startswith(('short:', 'long:'))   # '123' -> 3 digits


def test_apply_anonymization_with_filter_condition(dpetl_package):
    """Only rows matching the filter expression get anonymized."""
    resource = dpetl_package.get_resource('anonymized')
    field = field_by_name(resource, 'col5')
    table = resource.to_petl()

    data = list(anonymize.apply_anonymization(field, table, None))

    col_index = data[0].index('col5')
    # flag == x for rows 1 and 3, y for row 2 (see anonymized.csv)
    assert data[1][col_index] != 'fval1' and len(data[1][col_index]) == 16
    assert data[2][col_index] == 'fval2'
    assert data[3][col_index] != 'fval3' and len(data[3][col_index]) == 16


# Tests for apply_anonymization - error/edge cases (synthetic field) -----------
def test_apply_anonymization_aes_siv_missing_key(caplog):
    """aes_siv without a secret_key exits instead of silently proceeding."""
    caplog.set_level(logging.ERROR)
    field = make_field({'method': 'aes_siv'})
    table = etl.wrap([['col1'], ['value1']])

    with pytest.raises(SystemExit):
        anonymize.apply_anonymization(field, table, None)

    assert 'Missing required environment variable' in caplog.text


def test_apply_anonymization_filter_exception():
    """A filter expression that raises falls back to the original value."""
    field = make_field({'method': 'sha256', 'filter': '1/0'})
    table = etl.wrap([['col1'], ['value1']])

    data = list(anonymize.apply_anonymization(field, table, None))

    assert data[1][0] == 'value1'


def test_apply_anonymization_invalid_method(caplog):
    """An unrecognized method exits instead of silently passing values through."""
    caplog.set_level(logging.ERROR)
    field = make_field({'method': 'invalid'})
    table = etl.wrap([['col1'], ['value1']])

    with pytest.raises(SystemExit):
        anonymize.apply_anonymization(field, table, None)

    assert 'Unknown anonymize method' in caplog.text


def test_apply_anonymization_missing_values():
    """Configured missing values are left untouched instead of being anonymized."""
    field = make_field({'method': 'sha256'}, missing_values=['NA', ''])
    table = etl.wrap([['col1'], ['value1'], ['NA'], ['']])

    data = list(anonymize.apply_anonymization(field, table, None))

    assert data[1][0] != 'value1' and len(data[1][0]) == 16
    assert data[2][0] == 'NA'
    assert data[3][0] == ''


# Tests for build_constraints --------------------------------------------------
def test_build_constraints_sha256():
    """sha256 produces a 16-char hex pattern."""
    field = make_field({'method': 'sha256'}, constraints={})
    pattern = anonymize.build_constraints(field)['pattern']

    assert pattern == '^[0-9a-f]{16}$'
    assert re.match(pattern, '0123456789abcdef')
    assert not re.match(pattern, '0123456789abcde')


def test_build_constraints_aes_siv_with_annotation():
    """aes_siv with annotation produces one alternative per label, all 32-char hex."""
    field = make_field({'method': 'aes_siv', 'annotation': 'CPF:11|CNPJ:14'}, constraints={})

    pattern = anonymize.build_constraints(field)['pattern']

    assert pattern == r'^(CPF:[0-9a-f]{32}|CNPJ:[0-9a-f]{32})$'


def test_build_constraints_sha256_with_annotation():
    """sha256 with annotation includes every label in the pattern."""
    field = make_field({'method': 'sha256', 'annotation': 'short:1|long:2'}, constraints={})

    pattern = anonymize.build_constraints(field)['pattern']

    assert 'short:' in pattern and 'long:' in pattern


@pytest.mark.parametrize('method, matches', [
    ('[###-###]', ['123-456']),
    ('[###-###|####-####]', ['123-456', '1234-5678']),
])
def test_build_constraints_mask_patterns(method, matches):
    """Mask patterns with one or more variants produce a matching regex."""
    field = make_field({'method': method}, constraints={})
    pattern = anonymize.build_constraints(field)['pattern']

    for value in matches:
        assert re.match(pattern, value), f'Pattern {pattern} did not match {value}'


def test_build_constraints_mask_no_literals():
    """A variant with only # and * matches any string not starting with *."""
    field = make_field({'method': '[###|****]'}, constraints={})
    pattern = anonymize.build_constraints(field)['pattern']

    assert re.match(pattern, '123')
    assert re.match(pattern, 'abc')
    assert not re.match(pattern, '*abc')


def test_build_constraints_mask_with_star_and_literals():
    """A mask mixing * and literal digits keeps the literal * and matches \\d for #."""
    field = make_field({'method': '[***-###]'}, constraints={})
    pattern = anonymize.build_constraints(field)['pattern']

    assert pattern == r'^\*\*\*\-\d{3}$'
    assert re.match(pattern, '***-123')
    assert not re.match(pattern, 'abc-123')


def test_build_constraints_literal_mask():
    """A literal mask (no # or *) matches only that exact literal."""
    field = make_field({'method': '[INFORMACAO COM RESTRICAO DE ACESSO]'}, constraints={})

    constraints = anonymize.build_constraints(field)

    assert constraints['pattern'] == r'^INFORMACAO\ COM\ RESTRICAO\ DE\ ACESSO$'


def test_build_constraints_with_filter_and_no_original_pattern():
    """A filter with no original pattern to fall back to returns no constraint at all."""
    field = make_field({'method': 'sha256', 'filter': 'x'}, constraints={})

    assert anonymize.build_constraints(field) == {}


def test_build_constraints_with_filter_and_original_pattern():
    """A filter combines the original pattern with the anonymized token pattern."""
    field = make_field({'method': 'sha256', 'filter': 'x'}, constraints={'pattern': '^[0-9]{3}$'})

    pattern = anonymize.build_constraints(field)['pattern']

    assert re.match(pattern, '123')
    assert re.match(pattern, '0123456789abcdef')
    assert not re.match(pattern, 'abc')


def test_build_constraints_no_method():
    """No anonymize method (absent or empty) returns the field's original constraints."""
    field = make_field(constraints={'required': True})
    assert anonymize.build_constraints(field) == {'required': True}

    field = make_field({}, constraints={'minLength': 5})
    assert anonymize.build_constraints(field) == {'minLength': 5}
