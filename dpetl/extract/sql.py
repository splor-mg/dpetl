import logging
import os
from pathlib import Path

import petl as etl
from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger(__name__)


def extract_sql(resource, **kwargs):
    """
    Run a query on a database and save the result to `resource.path`.

    The connection is a SQLAlchemy URL read from the environment variable
    `DATABASE_URL`. The query is `query`, or `SELECT * FROM <table>` when
    `table` is given, or else the content of the file in `query_file`
    (relative to the descriptor, defaults to `sql/<resource name>.sql`).
    """
    try:
        from sqlalchemy import create_engine
    except ImportError:
        logger.error(
            'SQL extraction requires the sql extra: pip install dpetl[sql]'
        )
        return

    config = resource.custom.get('dpetl_extract', {})

    load_dotenv(find_dotenv(usecwd=True))
    url = os.environ.get('DATABASE_URL')

    if not url:
        logger.error(
            'Missing environment variable "DATABASE_URL" for resource %s.',
            resource.name,
        )
        return

    basepath = Path(resource.package._basepath)
    query_file = basepath / config.get(
        'query_file', f'sql/{resource.name}.sql'
    )

    if 'query' in config:
        query = config['query']
    elif 'table' in config:
        query = f'SELECT * FROM {config["table"]}'
    elif query_file.exists():
        query = query_file.read_text(encoding='utf-8').strip().rstrip(';')
    else:
        logger.error(
            'Missing query for resource %s: set dpetl_extract.query, '
            'dpetl_extract.query_file or dpetl_extract.table, or create %s',
            resource.name,
            query_file,
        )
        return

    logger.debug('Running query for resource %s: %s', resource.name, query)

    with create_engine(url).connect() as connection:
        table = etl.fromdb(connection.connection, query)
        write_file(table, basepath / resource.path, config)


def write_file(table, path, config):
    """
    Save a PETL table to `path`. CSV files use `encoding` (defaults to `utf-8`)
    and `delimiter` (defaults to `,`).
    """
    encoding = config.get('encoding') or 'utf-8'
    delimiter = config.get('delimiter') or ','

    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix == '.xlsx':
        etl.toxlsx(table, str(path))
    else:
        etl.tocsv(table, str(path), encoding=encoding, delimiter=delimiter)

    logger.info('Saved %s.', path)
