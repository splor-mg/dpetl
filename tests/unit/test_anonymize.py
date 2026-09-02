"""
Unit tests for the anonymize module: field masking, hashing, and schema constraints.
"""
import pytest
import logging
import re
import petl as etl

from dpetl.transform import anonymize


# Tests for _apply_mask --------------------------------------------------------
def test_apply_mask_basic():
    """Test mask with separators."""
    assert anonymize._apply_mask('[###-###]', '123456') == '123-456'
    assert anonymize._apply_mask('[***-***]', '123456') == '***-***'
    assert anonymize._apply_mask('[##* - ##*]', '123456') == '12* - 45*'


def test_apply_mask_multiple_variants():
    """Test mask with multiple variants based on digit count."""
    pattern = '[###-####|#####-###]'
    assert anonymize._apply_mask(pattern, '1234567') == '123-4567'
    assert anonymize._apply_mask(pattern, '12345678') == '12345-678'
    assert anonymize._apply_mask(pattern, '12') == '12'


def test_apply_mask_literal_fixed():
    """Test mask with a fixed literal (no # or *)."""
    assert anonymize._apply_mask('[abc]', 'anything') == 'abc'


def test_apply_mask_character_masking():
    """Test mask that preserves first character and masks the rest."""
    assert anonymize._apply_mask('[#*****]', 'Maria') == 'M****'
    assert anonymize._apply_mask('[*****]', 'João') == '****'


def test_apply_mask_cpf_cnpj():
    """Test CPF and CNPJ masks."""
    cpf = '12345678909'
    cnpj = '12345678000199'
    assert anonymize._apply_mask('[###.###.###-##]', cpf) == '123.456.789-09'
    assert anonymize._apply_mask('[***.###.###-**]', cpf) == '***.456.789-**'
    assert anonymize._apply_mask('[##.###.###/####-##]', cnpj) == '12.345.678/0001-99'
    assert anonymize._apply_mask('[**.###.###/****-##]', cnpj) == '**.345.678/****-99'


# Tests for apply_anonymization ------------------------------------------------
def test_apply_anonymization_sha256():
    """Test anonymization with sha256 method."""
    field = type('Field', (), {
        'name': 'col1',
        'missing_values': [],
        'custom': {'anonymize': {'method': 'sha256'}}
    })()
    table = etl.wrap([['col1'], ['value1'], ['value2']])
    result = anonymize.apply_anonymization(field, table, None)
    data = list(result)
    assert data[0] == ('col1',)
    assert data[1][0] != 'value1'
    assert len(data[1][0]) == 16
    assert data[2][0] != 'value2'
    assert len(data[2][0]) == 16


def test_apply_anonymization_aes_siv():
    """Test anonymization with aes_siv and secret key."""
    field = type('Field', (), {
        'name': 'col1',
        'missing_values': [],
        'custom': {'anonymize': {'method': 'aes_siv'}}
    })()
    secret_key = '0123456789abcdef0123456789abcdef'
    table = etl.wrap([['col1'], ['value1']])
    result = anonymize.apply_anonymization(field, table, secret_key)
    data = list(result)
    assert data[0] == ('col1',)
    assert len(data[1][0]) == 32
    # Deterministic
    result2 = anonymize.apply_anonymization(field, table, secret_key)
    assert list(result2)[1][0] == data[1][0]


def test_apply_anonymization_aes_siv_missing_key(caplog):
    """Test that aes_siv without secret_key raises SystemExit."""
    caplog.set_level(logging.ERROR)
    field = type('Field', (), {
        'name': 'col1',
        'missing_values': [],
        'custom': {'anonymize': {'method': 'aes_siv'}}
    })()
    table = etl.wrap([['col1'], ['value1']])
    with pytest.raises(SystemExit):
        anonymize.apply_anonymization(field, table, None)
    assert 'Missing required environment variable' in caplog.text


def test_apply_anonymization_mask_method():
    """Test apply_anonymization with a mask pattern method."""
    field = type('Field', (), {
        'name': 'col1',
        'missing_values': [],
        'custom': {'anonymize': {'method': '[###-###]'}}
    })()
    table = etl.wrap([['col1'], ['123456']])
    result = anonymize.apply_anonymization(field, table, None)
    data = list(result)
    assert data[1][0] == '123-456'


def test_apply_anonymization_with_annotation():
    """Test anonymization with annotation labels."""
    field = type('Field', (), {
        'name': 'col1',
        'missing_values': [],
        'custom': {
            'anonymize': {
                'method': 'sha256',
                'annotation': 'short:1|long:2'
            }
        }
    })()
    table = etl.wrap([['col1'], ['1'], ['12'], ['123']])
    result = anonymize.apply_anonymization(field, table, None)
    data = list(result)
    assert data[1][0].startswith('short:')
    assert data[2][0].startswith('long:')
    assert not data[3][0].startswith('short:') and not data[3][0].startswith('long:')


def test_apply_anonymization_aes_siv_with_annotation():
    """Test aes_siv with annotation labels."""
    field = type('Field', (), {
        'name': 'col1',
        'missing_values': [],
        'custom': {
            'anonymize': {
                'method': 'aes_siv',
                'annotation': 'CPF:11|CNPJ:14'
            }
        }
    })()
    secret_key = '0123456789abcdef0123456789abcdef'
    table = etl.wrap([['col1'], ['12345678909'], ['12345678000199']])
    result = anonymize.apply_anonymization(field, table, secret_key)
    data = list(result)
    assert data[1][0].startswith('CPF:')
    assert data[2][0].startswith('CNPJ:')
    assert len(data[1][0]) > 4
    assert len(data[2][0]) > 5


def test_apply_anonymization_with_filter_condition():
    """
    Test that filter condition is evaluated and anonymization applied only when true.
    """
    field = type('Field', (), {
        'name': 'col1',
        'missing_values': [],
        'custom': {
            'anonymize': {
                'method': 'sha256',
                'filter': 'col2 == "x"'
            }
        }
    })()
    table = etl.wrap([['col1', 'col2'], ['value1', 'x'], ['value2', 'y']])
    result = anonymize.apply_anonymization(field, table, None)
    data = list(result)
    assert data[1][0] != 'value1' and len(data[1][0]) == 16
    assert data[2][0] == 'value2'   # condition false


def test_apply_anonymization_filter_exception():
    """Test that an exception in filter evaluation returns original value."""
    field = type('Field', (), {
        'name': 'col1',
        'missing_values': [],
        'custom': {'anonymize': {'method': 'sha256', 'filter': '1/0'}}
    })()
    table = etl.wrap([['col1'], ['value1']])
    result = anonymize.apply_anonymization(field, table, None)
    data = list(result)
    assert data[1][0] == 'value1'


def test_apply_anonymization_invalid_method(caplog):
    """Test that an invalid anonymization method raises SystemExit."""
    caplog.set_level(logging.ERROR)
    field = type('Field', (), {
        'name': 'col1',
        'missing_values': [],
        'custom': {'anonymize': {'method': 'invalid'}}
    })()
    table = etl.wrap([['col1'], ['value1']])
    with pytest.raises(SystemExit):
        anonymize.apply_anonymization(field, table, None)
    assert "Unknown anonymize method" in caplog.text


# Tests for build_constraints --------------------------------------------------
def test_build_constraints_aes_siv_with_annotation():
    """Test build_constraints for aes_siv with annotation."""
    field = type('Field', (), {
        'custom': {
            'anonymize': {
                'method': 'aes_siv',
                'annotation': 'CPF:11|CNPJ:14'
            }
        },
        'constraints': {}
    })()
    constraints = anonymize.build_constraints(field)
    pattern = constraints['pattern']
    assert pattern == r'^(CPF:[0-9a-f]{32}|CNPJ:[0-9a-f]{32})$'


def test_build_constraints_sha256():
    """Test constraint generation for sha256."""
    field = type('Field', (), {
        'custom': {'anonymize': {'method': 'sha256'}},
        'constraints': {}
    })()
    constraints = anonymize.build_constraints(field)
    assert constraints['pattern'] == '^[0-9a-f]{16}$'
    assert re.match(constraints['pattern'], '0123456789abcdef')
    assert not re.match(constraints['pattern'], '0123456789abcde')


def test_build_constraints_sha256_with_annotation():
    """Test constraint generation for sha256 with annotation."""
    field = type('Field', (), {
        'custom': {
            'anonymize': {
                'method': 'sha256',
                'annotation': 'short:1|long:2'
            }
        },
        'constraints': {}
    })()
    constraints = anonymize.build_constraints(field)
    pattern = constraints['pattern']
    assert 'short:' in pattern and 'long:' in pattern


@pytest.mark.parametrize('method, matches', [
    ('[###-###]', ['123-456']),
    ('[###-###|####-####]', ['123-456', '1234-5678']),
])
def test_build_constraints_mask_patterns(method, matches):
    """
    Test constraint generation for mask patterns with single and multiple variants.
    """
    field = type('Field', (), {
        'custom': {'anonymize': {'method': method}},
        'constraints': {}
    })()
    constraints = anonymize.build_constraints(field)
    pattern = constraints['pattern']
    for value in matches:
        assert re.match(pattern, value), f"Pattern {pattern} did not match {value}"


def test_build_constraints_mask_no_literals():
    """Test build_constraints when a mask variant has only # and *."""
    field = type('Field', (), {
        'custom': {'anonymize': {'method': '[###|****]'}},
        'constraints': {}
    })()
    constraints = anonymize.build_constraints(field)
    pattern = constraints['pattern']
    assert re.match(pattern, '123')      # matches ###
    assert re.match(pattern, 'abc')      # matches **** (any string not starting with *)
    assert not re.match(pattern, '*abc') # starts with * so fails


def test_build_constraints_mask_with_star_and_literals():
    """Test build_constraints with a mask containing * and literals."""
    field = type('Field', (), {
        'custom': {'anonymize': {'method': '[***-###]'}},
        'constraints': {}
    })()
    constraints = anonymize.build_constraints(field)
    pattern = constraints['pattern']
    assert pattern == r'^\*\*\*\-\d{3}$'
    assert re.match(pattern, '***-123')
    assert not re.match(pattern, 'abc-123')


def test_build_constraints_literal_mask():
    """Test build_constraints for a literal mask (no # or *)."""
    field = type('Field', (), {
        'custom': {'anonymize': {'method': '[INFORMACAO COM RESTRICAO DE ACESSO]'}},
        'constraints': {}
    })()
    constraints = anonymize.build_constraints(field)
    assert constraints['pattern'] == r'^INFORMACAO\ COM\ RESTRICAO\ DE\ ACESSO$'


def test_build_constraints_with_filter_and_no_original_pattern():
    """
    Test build_constraints with filter but no original pattern -> returns {}.
    """
    field = type('Field', (), {
        'custom': {'anonymize': {'method': 'sha256', 'filter': 'x'}},
        'constraints': {}
    })()
    constraints = anonymize.build_constraints(field)
    assert constraints == {}


def test_build_constraints_with_filter_and_original_pattern():
    """Test build_constraints with filter and original pattern."""
    field = type('Field', (), {
        'custom': {'anonymize': {'method': 'sha256', 'filter': 'x'}},
        'constraints': {'pattern': '^[0-9]{3}$'}
    })()
    constraints = anonymize.build_constraints(field)
    pattern = constraints['pattern']
    assert re.match(pattern, '123')                # original pattern
    assert re.match(pattern, '0123456789abcdef')   # anonymized token
    assert not re.match(pattern, 'abc')            # neither
