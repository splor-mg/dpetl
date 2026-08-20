"""
Unit tests for the anonymize module: field masking, hashing, and schema constraints.
"""
import pytest
import logging
import re

from dpetl.transform import anonymize


def test_apply_mask_basic():
    """
    Test mask pattern application.
    """
    # Pattern with fixed separators
    assert anonymize._apply_mask('[###-###]', '123456') == '123-456'

    # Pattern with mask all digits (*)
    assert anonymize._apply_mask('[***-***]', '123456') == '***-***'

    # Pattern with mixed
    assert anonymize._apply_mask('[##* - ##*]', '123456') == '12* - 45*'


def test_apply_mask_multiple_variants():
    """
    Test mask with multiple variants based on digit count.
    """
    pattern = '[###-####|#####-###]'

    # 7 digits: first variant
    assert anonymize._apply_mask(pattern, '1234567') == '123-4567'

    # 8 digits: second variant
    assert anonymize._apply_mask(pattern, '12345678') == '12345-678'

    # No match, return original
    assert anonymize._apply_mask(pattern, '12') == '12'


def test_apply_mask_no_match():
    """
    Test mask with multiple variants and a digit count that doesn't match any variant.
    """
    pattern = '[###-###|#####-###]'
    assert anonymize._apply_mask(pattern, '12345') == '12345'


def test_apply_mask_from_anonymize_no_match():
    """
    Test that _apply_mask returns the original value when no variant matches,
    called via apply_anonymization with a mask method.
    """
    field = type('Field', (), {
        'name': 'col1',
        'missing_values': [],
        'custom': {'anonymize': {'method': '[###-###|####-####]'}}
    })()
    table = [['col1'], ['12345']]
    result = anonymize.apply_anonymization(field, table, None)
    data = list(result)

    assert data[1][0] == '12345'


def test_apply_anonymization_sha256(monkeypatch):
    """
    Test anonymization with sha256 method.
    """
    field = type('Field', (), {
        'name': 'col1',
        'missing_values': [],
        'custom': {'anonymize': {'method': 'sha256'}}
    })()
    table = [['col1'], ['value1'], ['value2']]
    result = anonymize.apply_anonymization(field, table, None)

    # Convert back to list to check
    data = list(result)

    # Should have same number of rows, and values should be hashed
    assert len(data) == 3
    assert data[0] == ('col1',)
    assert data[1][0] != 'value1'
    assert len(data[1][0]) == 16
    assert data[2][0] != 'value2'


def test_apply_anonymization_aes_siv_missing_key(monkeypatch, caplog):
    """
    Test that aes_siv requires ANONYMIZE_SECRET_KEY.
    """
    field = type('Field', (), {
        'name': 'col1',
        'missing_values': [],
        'custom': {'anonymize': {'method': 'aes_siv'}}
    })()
    table = [['col1'], ['value1']]

    with pytest.raises(SystemExit):
        anonymize.apply_anonymization(field, table, None)

    assert 'Missing required environment variable' in caplog.text


def test_apply_anonymization_aes_siv(monkeypatch):
    """
    Test anonymization with aes_siv and secret key.
    """
    field = type('Field', (), {
        'name': 'col1',
        'missing_values': [],
        'custom': {'anonymize': {'method': 'aes_siv'}}
    })()
    secret_key = '0123456789abcdef0123456789abcdef'
    table = [['col1'], ['value1']]
    result = anonymize.apply_anonymization(field, table, secret_key)
    data = list(result)
    assert data[0] == ('col1',)
    assert len(data[1][0]) == 32

    # Repeat with same value, should produce same token (deterministic with key)
    result2 = anonymize.apply_anonymization(field, table, secret_key)
    assert list(result2)[1][0] == data[1][0]


def test_apply_anonymization_with_annotation():
    """
    Test anonymization with annotation labels.
    """
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
    secret_key = None
    table = [['col1'], ['1'], ['12'], ['123']]
    result = anonymize.apply_anonymization(field, table, secret_key)
    data = list(result)
    # 1 dígito -> label 'short:'
    assert data[1][0].startswith('short:')
    # 2 dígitos -> label 'long:'
    assert data[2][0].startswith('long:')
    # 3 dígitos -> without label
    assert not data[3][0].startswith('short:') and not data[3][0].startswith('long:')


def test_apply_anonymization_invalid_method(caplog):
    """
    Test that an invalid anonymization method raises SystemExit.
    """
    caplog.set_level(logging.ERROR)
    field = type('Field', (), {
        'name': 'col1',
        'missing_values': [],
        'custom': {'anonymize': {'method': 'invalid'}}
    })()
    table = [['col1'], ['value1']]

    with pytest.raises(SystemExit):
        anonymize.apply_anonymization(field, table, None)

    assert "Unknown anonymize method" in caplog.text


def test_build_constraints_mask():
    """
    Test constraint generation for mask patterns.
    """
    field = type('Field', (), {
        'custom': {'anonymize': {'method': '[###-###|####-####]'}},
        'constraints': {}
    })()
    constraints = anonymize.build_constraints(field)

    # Should produce regex with alternatives
    pattern = constraints['pattern']
    assert re.match(pattern, '123-456')
    assert re.match(pattern, '1234-5678')


def test_build_constraints_mask_single_variant():
    """
    Test constraint generation for a single mask variant.
    """
    field = type('Field', (), {
        'custom': {'anonymize': {'method': '[###-###]'}},
        'constraints': {}
    })()
    constraints = anonymize.build_constraints(field)
    pattern = constraints['pattern']

    assert re.match(pattern, '123-456') is not None
    assert re.match(pattern, '1234-456') is None
    assert not re.match(pattern, '12-345')


def test_build_constraints_mask_with_star():
    """
    Test constraint generation for a mask variant that uses '*' (mask all digits).
    """
    field = type('Field', (), {
        'custom': {'anonymize': {'method': '[***-***]'}},
        'constraints': {}
    })()
    constraints = anonymize.build_constraints(field)
    pattern = constraints['pattern']

    assert re.match(pattern, '***-***') is not None
    assert re.match(pattern, '123-456') is None


def test_build_constraints_sha256():
    """
    Test constraint generation for sha256.
    """
    field = type('Field', (), {
        'custom': {'anonymize': {'method': 'sha256'}},
        'constraints': {}
    })()
    constraints = anonymize.build_constraints(field)
    pattern = constraints['pattern']

    assert pattern == '^[0-9a-f]{16}$'
    assert re.match(pattern, '0123456789abcdef')
    assert not re.match(pattern, '0123456789abcde')


def test_build_constraints_sha256_with_annotation():
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
