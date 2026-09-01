import re
import hashlib
import logging

import petl as etl
from cryptography.hazmat.primitives.ciphers.aead import AESSIV

logger = logging.getLogger(__name__)


# Anonymization methods: name -> (function, fixed output length in hex chars)
ANONYMIZE_METHODS = {
    'aes_siv': (
        lambda value, key, context=None: AESSIV(hashlib.sha512(key).digest()).encrypt(
            value.encode(), [context] if context else None
        )[:16].hex(),
        32,
    ),
    'sha256': (
        lambda value, key, context=None: hashlib.sha256(value.encode()).hexdigest()[:16],
        16,
    ),
}


def _apply_mask(pattern, value):
    """
    Apply a mask pattern to a value.
    # preserves the original digit, * masks it, any other character is a literal.
    """
    variants = pattern[1:-1].split('|')

    # Fixed literal (no # or *)
    if len(variants) == 1 and not any(c in '#*' for c in variants[0]):
        return variants[0]

    value_str = str(value)

    # Select variant based on digit count (if multiple variants)
    if len(variants) > 1:
        digit_count = sum(c.isdigit() for c in value_str)
        by_count = {sum(1 for c in v if c in '#*'): v for v in variants}
        variant = by_count.get(digit_count)
        if variant is None:
            return value_str
    else:
        variant = variants[0]

    # Check if there are literals in the pattern
    has_literals = any(c not in '#*' for c in variant)

    if has_literals:
        # Process only digits, keep literals
        source = iter(c for c in value_str if c.isdigit())
    else:
        # Process all characters
        source = iter(value_str)

    result = []
    for p in variant:
        if p in '#*':
            c = next(source, None)
            if c is None:
                break
            result.append(c if p == '#' else '*')
        else:
            result.append(p)

    return ''.join(result)


def apply_anonymization(field, table, secret_key, target=None):
    """
    Apply anonymization transforms for fields that declare an `anonymize` property.
    """
    config = field.custom.get('anonymize')
    if not config:
        return table

    method = config.get('method')
    missing_set = set(field.missing_values)
    condition = config.get('filter')
    header = table.header()

    # Apply mask-based anonymization
    if method.startswith('[') and method.endswith(']'):
        def transform(value, row):
            return _apply_mask(method, value)

    # Apply hash- or encryption-based anonymization
    else:
        if method not in ANONYMIZE_METHODS:
            logger.error(
                'Unknown anonymize method "%s" on field "%s". Supported methods: %s.',
                method, field.name, ', '.join(ANONYMIZE_METHODS) + ', [pattern]',
            )
            raise SystemExit(1)

        # Require a secret key only for AES-SIV
        if method == 'aes_siv' and not secret_key:
            logger.error('Missing required environment variable: ANONYMIZE_SECRET_KEY.')
            raise SystemExit(1)

        fn, _ = ANONYMIZE_METHODS[method]
        key = secret_key.encode() if secret_key else None
        context_field = config.get('context')
        annotation = config.get('annotation')

        # Build label mapping for values with different digit counts
        annotation_labels = {}
        if annotation:
            for pair in annotation.split('|'):
                label, digit_count = pair.split(':')
                annotation_labels[int(digit_count)] = label

        def transform(value, row):
            # Apply optional context and the selected anonymization method
            context = str(row[context_field]).encode() if context_field else None
            token = fn(str(value), key, context)

            digit_count = sum(c.isdigit() for c in str(value))
            label = annotation_labels.get(digit_count)

            return f'{label}:{token}' if label else token

    # Keep configured missing values unchanged
    def converter(value, row):
        if value in missing_set:
            return value
        if condition:
            namespace = dict(zip(header, row))
            try:
                matches = eval(condition, {}, namespace)
            except Exception:
                return value
            if not matches:
                return value
        return transform(value, row)

    logger.debug('Anonymizing field "%s" using method "%s".', field.name, method)
    return etl.convert(table, target or field.name, converter, pass_row=True)


def build_constraints(field):
    """
    Build schema constraints describing the shape of an anonymized field's output.
    """
    config = field.custom.get('anonymize') or {}
    method = config.get('method')

    if not method:
        return field.constraints

    # Build regex constraints for mask-based anonymization
    if method.startswith('[') and method.endswith(']'):
        parts = []
        for variant in method[1:-1].split('|'):
            if not any(c in '#*' for c in variant):
                parts.append(re.escape(variant))
                continue
            if all(c in '#*' for c in variant):
                parts.append(r'[^*].*')
                continue

            regex_chars = []
            for c in variant:
                if c == '#':
                    regex_chars.append(r'\d')
                elif c == '*':
                    regex_chars.append(r'\*')
                else:
                    regex_chars.append(re.escape(c))

            pattern = ''.join(regex_chars)
            pattern = re.sub(
                r'(\\d){2,}',
                lambda m: rf'\d{{{len(m.group()) // 2}}}',
                pattern
            )
            parts.append(pattern)

    # Build regex constraints for hash- or encryption-based anonymization
    else:
        _, length = ANONYMIZE_METHODS[method]
        token = f'[0-9a-f]{{{length}}}'
        annotation = config.get('annotation')

        if annotation:
            labels = [pair.split(':')[0] for pair in annotation.split('|')]
            parts = [f'{label}:{token}' for label in labels]
        else:
            parts = [token]

    pattern_str = '|'.join(parts)

    # With a filter, non-matching rows keep their original format
    if config.get('filter'):
        original_pattern = (field.constraints or {}).get('pattern')
        if original_pattern:
            combined = f'{original_pattern.strip("^$")}|{pattern_str}'
            return {'pattern': f'^({combined})$'}
        else:
            return {}

    return {'pattern': f'^({pattern_str})$' if len(parts) > 1 else f'^{pattern_str}$'}
