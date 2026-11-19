"""
Integration tests for the postgres module against a real database.
They run only when PG_TEST_URL points to a database that can be written to;
each test uses its own schema, dropped at the end.
"""
import os
import gzip
import json
import uuid
import pytest
from frictionless import Package, Resource

from dpetl.load import postgres

PG_TEST_URL = os.environ.get('PG_TEST_URL')

pytestmark = pytest.mark.skipif(not PG_TEST_URL, reason='PG_TEST_URL is not set')


@pytest.fixture
def schema(monkeypatch):
    """A unique schema for the test, removed afterwards."""
    psycopg = pytest.importorskip('psycopg')
    monkeypatch.setenv('PG_URL', PG_TEST_URL)
    name = f'dpetl_test_{uuid.uuid4().hex[:8]}'

    yield name

    with psycopg.connect(PG_TEST_URL) as connection:
        connection.execute(f'DROP SCHEMA IF EXISTS {name} CASCADE')


def query(sql):
    import psycopg

    with psycopg.connect(PG_TEST_URL) as connection:
        return connection.execute(sql).fetchall()


def query_execute(sql):
    import psycopg

    with psycopg.connect(PG_TEST_URL) as connection:
        connection.execute(sql)


def make_package(tmp_path, resources):
    """Write each resource as a gzip CSV and build a transformed-like package."""
    (tmp_path / 'data').mkdir(parents=True, exist_ok=True)
    package = Package(basepath=str(tmp_path))

    for name, (csv, fields, delimiter) in resources.items():
        path = f'data/{name}.csv.gz'
        with gzip.open(tmp_path / path, 'wt', encoding='utf-8') as file:
            file.write(csv)

        descriptor = {
            'name': name,
            'path': path,
            'format': 'csv',
            'compression': 'gz',
            'encoding': 'utf-8',
            'schema': {'fields': fields},
        }
        if delimiter != ',':
            descriptor['dialect'] = {'csv': {'delimiter': delimiter}}
        package.add_resource(Resource.from_descriptor(descriptor))

    return package


FIELDS = [
    {'name': 'ano', 'type': 'integer'},
    {'name': 'orgao', 'type': 'string'},
    {'name': 'vlr_empenhado', 'type': 'number'},
    {'name': 'data', 'type': 'date'},
]


def test_load_tables_creates_typed_tables(tmp_path, schema):
    """Each resource becomes a table with Postgres types, including NULLs and custom delimiters."""
    package = make_package(tmp_path, {
        'execucao': (
            'ano;orgao;vlr_empenhado;data\n'
            '2024;A;100.5;2024-01-31\n'
            '2025;;;\n',
            FIELDS, ';',
        ),
    })

    descriptors = postgres.load_tables(package, schema)

    columns = query(
        "SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_schema = '{schema}' AND table_name = 'execucao' ORDER BY ordinal_position"
    )
    assert columns == [
        ('ano', 'bigint'), ('orgao', 'text'), ('vlr_empenhado', 'numeric'), ('data', 'date'),
    ]

    rows = query(f'SELECT ano, orgao, vlr_empenhado::text, data::text FROM {schema}.execucao ORDER BY ano')
    assert rows == [(2024, 'A', '100.5', '2024-01-31'), (2025, None, None, None)]

    assert descriptors[0]['dialect'] == {'sql': {'table': 'execucao', 'namespace': schema}}


def test_load_tables_replaces_previous_data(tmp_path, schema):
    """Loading again replaces the table instead of appending rows."""
    first = make_package(tmp_path / 'first', {
        'execucao': ('ano,orgao,vlr_empenhado,data\n2024,A,1,2024-01-01\n', FIELDS, ','),
    })
    second = make_package(tmp_path / 'second', {
        'execucao': ('ano,orgao,vlr_empenhado,data\n2025,B,2,2025-01-01\n', FIELDS, ','),
    })

    postgres.load_tables(first, schema)
    postgres.load_tables(second, schema)

    assert query(f'SELECT ano, orgao FROM {schema}.execucao') == [(2025, 'B')]


def test_load_tables_is_atomic(tmp_path, schema):
    """If one resource fails, no table of the package changes."""
    good = make_package(tmp_path / 'good', {
        'execucao': ('ano,orgao,vlr_empenhado,data\n2024,A,1,2024-01-01\n', FIELDS, ','),
    })
    postgres.load_tables(good, schema)

    broken = make_package(tmp_path / 'broken', {
        'execucao': ('ano,orgao,vlr_empenhado,data\n2025,B,2,2025-01-01\n', FIELDS, ','),
        'cota': ('ano,orgao,vlr_empenhado,data\nnot-a-year,B,2,2025-01-01\n', FIELDS, ','),
    })

    import psycopg
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        postgres.load_tables(broken, schema)

    assert query(f'SELECT ano, orgao FROM {schema}.execucao') == [(2024, 'A')]
    assert query(
        f"SELECT count(*) FROM information_schema.tables WHERE table_schema = '{schema}' AND table_name = 'cota'"
    ) == [(0,)]


def test_load_tables_drops_removed_resources_but_keeps_views(tmp_path, schema):
    """Tables of resources removed from the package are dropped; views are left alone."""
    row = 'ano,orgao,vlr_empenhado,data\n2024,A,1,2024-01-01\n'
    before = make_package(tmp_path / 'before', {
        'execucao': (row, FIELDS, ','),
        'cota': (row, FIELDS, ','),
    })
    postgres.load_tables(before, schema)
    query_execute(f'CREATE VIEW {schema}.resumo AS SELECT 1 AS um')

    after = make_package(tmp_path / 'after', {'execucao': (row, FIELDS, ',')})
    postgres.load_tables(after, schema)

    objects = query(
        f"SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = '{schema}' ORDER BY 1"
    )
    assert objects == [('execucao', 'BASE TABLE'), ('resumo', 'VIEW')]


def test_load_package_to_postgres(tmp_path, schema, monkeypatch):
    """End to end: data lands in Postgres and the committed descriptor points to the tables."""
    from dpetl.load import load

    package = make_package(tmp_path, {
        'execucao': ('ano,orgao,vlr_empenhado,data\n2024,A,1,2024-01-01\n', FIELDS, ','),
    })
    package.name = 'dados_siafi'
    package.custom['dpetl_load'] = {'owner': 'owner', 'repo': 'repo', 'target': 'postgres', 'schema': schema}

    committed = {}
    monkeypatch.setattr('dpetl.load.load._get_token', lambda *a: 'token')
    monkeypatch.setattr('dpetl.load.load.github.repo_exists', lambda *a, **k: True)
    monkeypatch.setattr('dpetl.load.load.github.get_deletions', lambda *a, **k: set())
    monkeypatch.setattr(
        'dpetl.load.load.github.commit_remote',
        lambda token, files, *a, **k: committed.update(files)
    )

    load.load_package(package)

    assert query(f'SELECT ano, orgao FROM {schema}.execucao') == [(2024, 'A')]

    descriptor = Package.from_descriptor(json.loads(committed['datapackage.json']))
    resource = descriptor.get_resource('execucao')
    assert (resource.scheme, resource.format) == ('postgresql', 'sql')
    assert '@' not in resource.path
