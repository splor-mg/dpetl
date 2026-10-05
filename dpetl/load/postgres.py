import os
import gzip
import logging
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)

# Frictionless field types mapped to Postgres column types (others are text)
TYPES = {
    'string': 'text',
    'integer': 'bigint',
    'number': 'numeric',
    'boolean': 'boolean',
    'date': 'date',
    'datetime': 'timestamp',
    'time': 'time',
    'year': 'integer',
}

FORMATS = ('csv', 'txt')

CHUNK_SIZE = 1024 * 1024


def get_url():
    """
    Retrieve the Postgres connection URL from environment variables.
    """
    url = os.environ.get('PG_URL')

    if not url:
        logger.error('Missing required environment variable: PG_URL.')
        raise SystemExit(1)

    return url


def get_public_url(url):
    """
    Remove the credentials from a connection URL so it can be published.
    """
    parts = urlsplit(url)
    netloc = parts.hostname or ''

    if parts.port:
        netloc = f'{netloc}:{parts.port}'

    return urlunsplit((parts.scheme, netloc, parts.path, '', ''))


def connect(url):
    """
    Open a Postgres connection.
    """
    try:
        import psycopg
    except ImportError:
        raise ImportError(
            'Postgres loading requires additional dependencies. '
            'Install them with: poetry install --extras postgres'
        )

    return psycopg.connect(url)


def create_table(cursor, schema, resource):
    """
    Recreate the resource table using its Table Schema field types.
    """
    from psycopg import sql

    table = sql.Identifier(schema, resource.name)
    columns = sql.SQL(', ').join(
        sql.SQL('{} {}').format(
            sql.Identifier(field.name),
            sql.SQL(TYPES.get(field.type, 'text')),
        )
        for field in resource.schema.fields
    )

    cursor.execute(sql.SQL('DROP TABLE IF EXISTS {}').format(table))
    cursor.execute(sql.SQL('CREATE TABLE {} ({})').format(table, columns))


def copy_resource(cursor, schema, resource, basepath):
    """
    Stream the resource file into its table with COPY.
    """
    from psycopg import sql

    if resource.format not in FORMATS:
        logger.error(
            'Resource %s has format %s. Postgres loading supports: %s.',
            resource.name, resource.format, ', '.join(FORMATS)
        )
        raise SystemExit(1)

    dialect = resource.dialect
    delimiter = (
        dialect.get_control('csv').delimiter
        if dialect.has_control('csv') else ','
    )

    statement = sql.SQL(
        'COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER true, DELIMITER {})'
    ).format(
        sql.Identifier(schema, resource.name),
        sql.SQL(', ').join(
            sql.Identifier(field.name) for field in resource.schema.fields
        ),
        sql.Literal(delimiter),
    )

    path = Path(basepath) / resource.path
    opener = gzip.open if resource.compression == 'gz' else open

    with opener(path, 'rt', encoding=resource.encoding or 'utf-8') as file:
        with cursor.copy(statement) as copy:
            while chunk := file.read(CHUNK_SIZE):
                copy.write(chunk)


def describe_table(resource, url, schema):
    """
    Point the resource descriptor to its Postgres table.
    """
    descriptor = resource.to_descriptor()

    # File location and file stats (hash, bytes) no longer describe the table
    for key in ('path', 'scheme', 'format', 'compression', 'encoding',
                'mediatype', 'extrapaths', 'dialect', 'hash', 'bytes'):
        descriptor.pop(key, None)

    descriptor['path'] = get_public_url(url)
    descriptor['dialect'] = {
        'sql': {'table': resource.name, 'namespace': schema}
    }

    return descriptor


def drop_removed_tables(cursor, schema, package):
    """
    Drop the tables of resources that no longer belong to the package.
    Only tables are dropped; views and other objects are kept.
    """
    from psycopg import sql

    cursor.execute(
        'SELECT table_name FROM information_schema.tables '
        "WHERE table_schema = %s AND table_type = 'BASE TABLE'",
        (schema,)
    )
    current = {resource.name for resource in package.resources}
    removed = sorted({row[0] for row in cursor.fetchall()} - current)

    if removed:
        logger.debug('Removing outdated tables: %s', ', '.join(removed))

    for table in removed:
        cursor.execute(
            sql.SQL('DROP TABLE {}').format(sql.Identifier(schema, table))
        )


def load_tables(package, schema):
    """
    Load every resource of the package into Postgres tables, in a single
    transaction. Returns the resource descriptors pointing to the tables.
    """
    from psycopg import sql

    url = get_url()

    with connect(url) as connection, connection.cursor() as cursor:
        cursor.execute(
            sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(
                sql.Identifier(schema)
            )
        )

        for resource in package.resources:
            logger.debug(
                'Loading resource %s into %s.%s.',
                resource.name, schema, resource.name
            )
            create_table(cursor, schema, resource)
            copy_resource(cursor, schema, resource, package._basepath)

        drop_removed_tables(cursor, schema, package)

    logger.info(
        'Successfully loaded %d tables into schema %s. Tables=[%s]',
        len(package.resources),
        schema,
        ', '.join(resource.name for resource in package.resources)
    )

    return [describe_table(resource, url, schema) for resource in package.resources]
