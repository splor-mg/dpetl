"""
Integration tests for the linktable operation: building fact tables and a
linktable across data packages and loading them into a single repository.
"""
import json
import pytest
import pandas as pd
from pathlib import Path
from frictionless import Package, Resource

from dpetl.linktable import linktable


def make_package(tmp_path, name, resources, dpetl_linktable=None, dpetl_load=None):
    """Write a transformed-like datapackage.json (plus its CSV files, with inferred
    schemas as update_metadata does) and load it."""
    folder = tmp_path / name
    (folder / 'data').mkdir(parents=True)

    descriptor = {'name': name, 'resources': []}
    for resource_name, csv in resources.items():
        (folder / 'data' / f'{resource_name}.csv').write_text(csv)
        resource = Resource(path=f'data/{resource_name}.csv', basepath=str(folder))
        resource.infer()
        descriptor['resources'].append(resource.to_dict())

    if dpetl_linktable is not None:
        descriptor['dpetl_linktable'] = dpetl_linktable
    descriptor['dpetl_load'] = dpetl_load or {'owner': 'someone', 'repo': name}

    path = folder / 'datapackage.json'
    path.write_text(json.dumps(descriptor))
    return Package(path)


@pytest.fixture
def capture_load(monkeypatch):
    """Replaces load_package, keeping the loaded package and its file contents
    (the files live in a temporary folder removed right after loading)."""
    calls = []

    def fake(package, **kwargs):
        files = {
            resource.path: pd.read_csv(Path(package.basepath) / resource.path, dtype=str)
            for resource in package.resources
        }
        calls.append({'package': package, 'files': files, 'kwargs': kwargs})

    monkeypatch.setattr('dpetl.load.load.load_package', fake)
    return calls


# Building the linktable -------------------------------------------------------
def test_linktable_packages_builds_fact_tables_and_linktable(tmp_path, capture_load):
    """Each listed resource becomes a fact table, and shared dimensions become a single column."""
    despesa = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,orgao,vlr_empenhado\n2024,A,100\n2024,B,200\n'},
        dpetl_linktable={'resource_list': ['execucao']},
    )
    receita = make_package(
        tmp_path, 'receita',
        {'arrecadacao': 'ano,uf,vlr_receita\n2024,MG,10\n'},
        dpetl_linktable={'resource_list': ['arrecadacao']},
    )

    linktable.linktable_packages([despesa, receita], no_validate=True)

    [call] = capture_load
    files = call['files']
    assert sorted(files) == [
        'data/fact_arrecadacao.csv.gz',
        'data/fact_execucao.csv.gz',
        'data/linktable.csv.gz',
    ]

    fact = files['data/fact_execucao.csv.gz']
    assert list(fact.columns) == ['key_execucao', 'vlr_empenhado']
    assert fact['key_execucao'].tolist() == ['2024|A', '2024|B']

    table = files['data/linktable.csv.gz']
    assert set(table.columns) == {'key_execucao', 'key_arrecadacao', 'ano', 'orgao', 'uf'}
    assert len(table) == 3


def test_linktable_packages_loads_to_linktable_repo(tmp_path, capture_load):
    """The destination package goes to the 'linktable' repo, reusing the source owner settings."""
    load_settings = {'owner': 'splor', 'repo': 'despesa', 'level': 'orgs', 'visibility': 'public'}
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable={'resource_list': ['execucao']},
        dpetl_load=load_settings,
    )

    linktable.linktable_packages([package], no_validate=True)

    [call] = capture_load
    assert call['package'].name == 'linktable'
    assert call['package'].custom['dpetl_load'] == {
        'owner': 'splor', 'repo': 'linktable', 'level': 'orgs', 'visibility': 'public',
    }
    assert call['kwargs'] == {'no_validate': True}


def test_linktable_packages_only_uses_listed_resources(tmp_path, capture_load):
    """Resources missing from resource_list are left out of the linktable."""
    package = make_package(
        tmp_path, 'despesa',
        {
            'execucao': 'ano,vlr_empenhado\n2024,100\n',
            'auxiliar': 'ano,vlr_outro\n2024,1\n',
        },
        dpetl_linktable={'resource_list': ['execucao']},
    )

    linktable.linktable_packages([package], no_validate=True)

    [call] = capture_load
    assert 'data/fact_auxiliar.csv.gz' not in call['files']
    assert [r.name for r in call['package'].resources] == ['fact_execucao', 'linktable']


# Package selection ------------------------------------------------------------
@pytest.mark.parametrize('dpetl_linktable', [None, False, {'enabled': False}])
def test_linktable_packages_skips_disabled_packages(tmp_path, capture_load, dpetl_linktable):
    """Packages without dpetl_linktable (or with it disabled) are skipped and nothing is loaded."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable=dpetl_linktable,
    )

    linktable.linktable_packages([package])

    assert capture_load == []


# Configuration errors ---------------------------------------------------------
@pytest.mark.parametrize('dpetl_linktable', [True, {'resource_list': []}])
def test_linktable_packages_requires_resource_list(tmp_path, capture_load, dpetl_linktable):
    """An enabled package without resource_list stops the process."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable=dpetl_linktable,
    )

    with pytest.raises(SystemExit):
        linktable.linktable_packages([package])

    assert capture_load == []


def test_linktable_packages_fails_on_unknown_resource(tmp_path, capture_load, caplog):
    """A resource_list entry that does not exist in the package stops the process."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable={'resource_list': ['execucao', 'inexistente']},
    )

    with pytest.raises(SystemExit):
        linktable.linktable_packages([package])

    assert 'Resources not found in package despesa: inexistente.' in caplog.text
    assert capture_load == []


def test_linktable_packages_fails_on_duplicated_resource_name(tmp_path, capture_load, caplog):
    """Two packages with a resource of the same name would overwrite each other's fact table."""
    packages = [
        make_package(
            tmp_path, name,
            {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
            dpetl_linktable={'resource_list': ['execucao']},
        )
        for name in ('despesa', 'despesa_2')
    ]

    with pytest.raises(SystemExit):
        linktable.linktable_packages(packages)

    assert 'Resource execucao exists in packages despesa and despesa_2.' in caplog.text
    assert capture_load == []


def test_linktable_packages_fails_on_divergent_load_settings(tmp_path, capture_load):
    """Packages targeting different owners cannot share a linktable repository."""
    packages = [
        make_package(
            tmp_path, name,
            {name: 'ano,vlr_valor\n2024,100\n'},
            dpetl_linktable={'resource_list': [name]},
            dpetl_load={'owner': owner, 'repo': name},
        )
        for name, owner in (('despesa', 'splor'), ('receita', 'outro'))
    ]

    with pytest.raises(SystemExit):
        linktable.linktable_packages(packages)

    assert capture_load == []
