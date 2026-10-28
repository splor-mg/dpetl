"""
Unit tests for the postgres module: connection settings and the published
resource descriptors (no database needed).
"""
import pytest
from frictionless import Resource

from dpetl.load import postgres


# Tests for get_url / get_public_url -------------------------------------------
def test_get_url(monkeypatch):
    """PG_URL is read from the environment."""
    monkeypatch.setenv('PG_URL', 'postgresql://user:pwd@host:5432/db')

    assert postgres.get_url() == 'postgresql://user:pwd@host:5432/db'


def test_get_url_missing(monkeypatch, caplog):
    """Without PG_URL the process exits instead of trying a default database."""
    monkeypatch.delenv('PG_URL', raising=False)

    with pytest.raises(SystemExit):
        postgres.get_url()

    assert 'Missing required environment variable: PG_URL.' in caplog.text


@pytest.mark.parametrize(('url', 'expected'), [
    ('postgresql://user:pwd@host:5432/db', 'postgresql://host:5432/db'),
    ('postgresql://user@host/db', 'postgresql://host/db'),
    ('postgresql://host:5432/db?sslmode=require', 'postgresql://host:5432/db'),
])
def test_get_public_url_removes_credentials(url, expected):
    """User, password and query options never reach the published descriptor."""
    assert postgres.get_public_url(url) == expected


# Tests for describe_table -----------------------------------------------------
def test_describe_table_points_to_postgres_table():
    """The descriptor keeps name/schema but swaps the file location for the table."""
    resource = Resource.from_descriptor({
        'name': 'execucao',
        'path': 'data/execucao.csv.gz',
        'format': 'csv',
        'compression': 'gz',
        'encoding': 'utf-8',
        'schema': {'fields': [{'name': 'ano', 'type': 'integer'}]},
        'hash': 'sha256:abc',
        'bytes': 10,
        'fields': 1,
        'rows': 2,
    })

    descriptor = postgres.describe_table(
        resource, 'postgresql://user:pwd@host:5432/db', 'dados_siafi'
    )

    assert descriptor['path'] == 'postgresql://host:5432/db'
    assert descriptor['dialect'] == {'sql': {'table': 'execucao', 'namespace': 'dados_siafi'}}
    assert descriptor['schema'] == {'fields': [{'name': 'ano', 'type': 'integer'}]}
    assert (descriptor['fields'], descriptor['rows']) == (1, 2)
    assert not {'compression', 'encoding', 'hash', 'bytes'} & descriptor.keys()

    # Frictionless reads it back as a SQL resource
    table = Resource.from_descriptor(descriptor)
    assert (table.scheme, table.format) == ('postgresql', 'sql')


# Tests for copy_resource ------------------------------------------------------
def test_copy_resource_rejects_unsupported_format(caplog):
    """Only delimited text files can be streamed with COPY."""
    resource = Resource.from_descriptor({
        'name': 'planilha',
        'path': 'data/planilha.xlsx',
        'schema': {'fields': [{'name': 'ano', 'type': 'integer'}]},
    })

    with pytest.raises(SystemExit):
        postgres.copy_resource(None, 'schema', resource, '/tmp')

    assert 'Resource planilha has format xlsx.' in caplog.text
