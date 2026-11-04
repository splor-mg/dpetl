import re
import logging

import petl as etl

logger = logging.getLogger(__name__)


def apply_replace(field, table):
    """
    Replace parts of the values of fields that declare a `replace` property.
    Each key is a regex replaced by its value, in order.
    Values that are not strings, such as missing values, are kept.
    """
    config = field.custom.get('replace')
    if not config:
        return table

    patterns = [
        (re.compile(pattern), replacement)
        for pattern, replacement in config.items()
    ]

    def converter(value):
        if not isinstance(value, str):
            return value
        for pattern, replacement in patterns:
            value = pattern.sub(replacement, value)
        return value

    logger.debug('Replacing values of field "%s".', field.name)
    return etl.convert(table, field.name, converter)
