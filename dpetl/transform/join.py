import logging
from collections import Counter
from pathlib import Path

import petl as etl
from frictionless import fields

logger = logging.getLogger(__name__)


def apply_join(field, table, report):
    """
    Add columns from a .csv file to fields that declare a `join` property.
    Rows without a match, or matching a key with different values in the file,
    are counted in `report` while the table is read.
    """
    config = field.custom.get('join')
    if not config:
        return table

    path = Path(config['path'])
    columns = config['columns']
    by = config.get('by', {})
    key = config.get('key', field.name)

    logger.debug('Joining columns %s to field "%s".', columns, field.name)

    if not path.exists():
        logger.error(
            'Join file "%s" not found for field "%s".',
            path, field.name,
        )
        raise SystemExit(1)

    # Map each key of the file to its values. Repeated keys keep the first values.
    matches = {}
    conflicts = set()

    for row in etl.dicts(etl.fromcsv(str(path), encoding='utf-8')):
        match_key = tuple(str(row[column]) for column in [*by.values(), key])
        values = tuple(row[column] for column in columns)

        if match_key not in matches:
            matches[match_key] = values
        elif matches[match_key] != values:
            conflicts.add(match_key)

    # Insert the matched values right after the field, empty when there is no match
    unmatched = (None,) * len(columns)
    header = list(etl.header(table))
    position = header.index(field.name) + 1
    header[position:position] = columns

    def add_columns(row):
        match_key = tuple(str(row[column]) for column in [*by, field.name])
        found = matches.get(match_key, unmatched)
        if found is unmatched:
            report.setdefault((field.name, 'without match'), Counter())[match_key] += 1
        elif match_key in conflicts:
            problem = 'with different values, kept the first'
            report.setdefault((field.name, problem), Counter())[match_key] += 1

        values = list(row)
        values[position:position] = found
        return values

    # failonerror makes petl raise instead of silently dropping rows
    return etl.rowmap(table, add_columns, header, failonerror=True)


def build_fields(field):
    """
    Build the schema fields of the columns added by a field's `join` property.
    """
    config = field.custom.get('join')
    if not config:
        return []

    return [
        fields.StringField(name=column)
        for column in config['columns']
    ]


def log_report(report):
    """
    Log the rows of each joined field without a match or with different values in the file.
    """
    for (name, problem), keys in report.items():
        logger.debug(
            'Join on field "%s": %s rows %s. Examples: %s.',
            name, sum(keys.values()), problem, sorted(keys, reverse=True)[:10],
        )
