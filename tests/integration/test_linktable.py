"""
Integration tests for the linktable operation: building fact tables and a
linktable, from one or several data packages, as a new data package.
"""
import json
import pytest
import pandas as pd
from frictionless import Package, Resource

from dpetl.linktable import linktable


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch):
    """Runs every test from tmp_path, where datapackages/<name> is written."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def make_package(tmp_path, name, resources, dpetl_linktable=None, folder=None):
    """Write a transformed-like datapackage.json (plus its CSV files, with inferred
    schemas as update_metadata does) and load it. 'folder' allows two packages
    with the same name (e.g. the same package in different years)."""
    folder = tmp_path / (folder or name)
    (folder / 'data').mkdir(parents=True)

    descriptor = {'name': name, 'resources': []}
    for resource_name, csv in resources.items():
        (folder / 'data' / f'{resource_name}.csv').write_text(csv)
        resource = Resource(path=f'data/{resource_name}.csv', basepath=str(folder))
        resource.infer()
        descriptor['resources'].append(resource.to_dict())

    if dpetl_linktable is not None:
        descriptor['dpetl_linktable'] = dpetl_linktable
    descriptor['dpetl_load'] = {'owner': 'someone', 'repo': name}

    path = folder / 'datapackage.json'
    path.write_text(json.dumps(descriptor))
    return Package(path)


def single(package):
    """The descriptor kwarg of a single -d pointing to the package."""
    return [package.metadata_descriptor_path]


def read_output(tmp_path, name):
    """Return the generated descriptor and the contents of its data files."""
    folder = tmp_path / 'datapackages' / name
    descriptor = json.loads((folder / 'datapackage.json').read_text())
    files = {
        path.name: pd.read_csv(path, dtype=str)
        for path in sorted((folder / 'data').iterdir())
    }
    return descriptor, files


# Across data packages ---------------------------------------------------------
def test_linktable_packages_builds_fact_tables_and_linktable(tmp_path):
    """Each listed resource becomes a fact table, and shared dimensions become a single column."""
    despesa = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,orgao,vlr_empenhado\n2024,A,100\n2024,B,200\n'},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
    )
    receita = make_package(
        tmp_path, 'receita',
        {'arrecadacao': 'ano,uf,vlr_receita\n2024,MG,10\n'},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['arrecadacao']},
    )

    linktable.linktable_packages([despesa, receita], name='orcamento')

    descriptor, files = read_output(tmp_path, 'orcamento')
    assert descriptor['name'] == 'orcamento'
    assert sorted(files) == [
        'fact_despesa_execucao.csv.gz',
        'fact_receita_arrecadacao.csv.gz',
        'linktable.csv.gz',
    ]

    fact = files['fact_despesa_execucao.csv.gz']
    assert list(fact.columns) == ['key_despesa_execucao', 'vlr_empenhado']
    assert fact['key_despesa_execucao'].tolist() == ['2024|A', '2024|B']

    table = files['linktable.csv.gz']
    assert set(table.columns) == {
        'key_despesa_execucao', 'key_receita_arrecadacao', 'ano', 'orgao', 'uf',
    }
    assert len(table) == 3


def test_linktable_packages_with_several_descriptors_is_across_packages(tmp_path):
    """Several -d also build the linktable across packages, so --name is required."""
    packages = [
        make_package(
            tmp_path, name,
            {name: 'ano,vlr_valor\n2024,100\n'},
            dpetl_linktable={'facts': ['vlr_*'], 'resource_list': [name]},
        )
        for name in ('despesa', 'receita')
    ]
    descriptor = [package.metadata_descriptor_path for package in packages]

    with pytest.raises(SystemExit):
        linktable.linktable_packages(packages, descriptor=descriptor)

    linktable.linktable_packages(packages, name='orcamento', descriptor=descriptor)

    _, files = read_output(tmp_path, 'orcamento')
    assert 'fact_despesa_despesa.csv.gz' in files


def test_linktable_packages_requires_name_across_packages(tmp_path, caplog):
    """Without -d, a missing --name stops the process before writing anything."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
    )

    with pytest.raises(SystemExit):
        linktable.linktable_packages([package])

    assert 'Missing "--name"' in caplog.text
    assert not (tmp_path / 'datapackages').exists()


# Single data package ----------------------------------------------------------
def test_linktable_packages_single_package(tmp_path):
    """A single -d builds <package>_linktable, with fact tables named after the resources."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,orgao,vlr_empenhado\n2024,A,100\n'},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
    )

    linktable.linktable_packages([package], descriptor=single(package))

    descriptor, files = read_output(tmp_path, 'despesa_linktable')
    assert descriptor['name'] == 'despesa_linktable'
    assert [r['path'] for r in descriptor['resources']] == [
        'data/fact_execucao.csv.gz',
        'data/linktable.csv.gz',
    ]
    assert list(files['fact_execucao.csv.gz'].columns) == ['key_execucao', 'vlr_empenhado']
    assert list(files['linktable.csv.gz'].columns) == ['key_execucao', 'ano', 'orgao']


def test_linktable_packages_single_package_with_name(tmp_path):
    """--name overrides the default name of a single package linktable."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
    )

    linktable.linktable_packages([package], name='outro', descriptor=single(package))

    descriptor, _ = read_output(tmp_path, 'outro')
    assert descriptor['name'] == 'outro'
    assert not (tmp_path / 'datapackages' / 'despesa_linktable').exists()


# Output package ---------------------------------------------------------------
def test_linktable_packages_writes_valid_package(tmp_path):
    """The generated descriptor is a valid data package, readable by load."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,orgao,vlr_empenhado\n2024,A,100\n2024,B,200\n'},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
    )

    linktable.linktable_packages([package], descriptor=single(package))

    output = Package(tmp_path / 'datapackages' / 'despesa_linktable' / 'datapackage.json')
    assert output.validate().valid
    assert 'updated_at' in output.custom


def test_linktable_packages_keeps_previous_metadata(tmp_path):
    """Regenerating the package keeps the user metadata (e.g. dpetl_load) and replaces the resources."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
    )
    folder = tmp_path / 'datapackages' / 'despesa_linktable'
    folder.mkdir(parents=True)
    (folder / 'datapackage.json').write_text(json.dumps({
        'name': 'despesa_linktable',
        'title': 'Despesa',
        'dpetl_load': {'owner': 'splor', 'repo': 'despesa-linktable'},
        'resources': [{'name': 'antigo', 'path': 'data/antigo.csv'}],
    }))

    linktable.linktable_packages([package], descriptor=single(package))

    descriptor, _ = read_output(tmp_path, 'despesa_linktable')
    assert descriptor['title'] == 'Despesa'
    assert descriptor['dpetl_load'] == {'owner': 'splor', 'repo': 'despesa-linktable'}
    assert [r['name'] for r in descriptor['resources']] == ['fact_execucao', 'linktable']


def test_linktable_packages_warns_without_dpetl_load(tmp_path, caplog):
    """A new linktable package has no dpetl_load yet: the user is told to set it."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
    )

    linktable.linktable_packages([package], descriptor=single(package))

    assert 'Set "dpetl_load"' in caplog.text


def test_linktable_packages_removes_stale_fact_tables(tmp_path):
    """A resource left out of resource_list leaves no fact table behind."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
    )
    data = tmp_path / 'datapackages' / 'despesa_linktable' / 'data'
    data.mkdir(parents=True)
    (data / 'fact_removido.csv.gz').write_text('x')

    linktable.linktable_packages([package], descriptor=single(package))

    assert sorted(path.name for path in data.iterdir()) == [
        'fact_execucao.csv.gz', 'linktable.csv.gz',
    ]


def test_linktable_packages_only_uses_listed_resources(tmp_path):
    """Resources missing from resource_list are left out of the linktable."""
    package = make_package(
        tmp_path, 'despesa',
        {
            'execucao': 'ano,vlr_empenhado\n2024,100\n',
            'auxiliar': 'ano,vlr_outro\n2024,1\n',
        },
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
    )

    linktable.linktable_packages([package], name='orcamento')

    descriptor, files = read_output(tmp_path, 'orcamento')
    assert 'fact_despesa_auxiliar.csv.gz' not in files
    assert [r['name'] for r in descriptor['resources']] == ['fact_despesa_execucao', 'linktable']


def test_linktable_packages_describes_comma_delimiter(tmp_path):
    """A fact table with only its key column is still described as comma-delimited,
    even though the keys contain '|' (which delimiter sniffing would pick)."""
    rows = ''.join(
        f'2002,{1000 + i},"CONSTRUCAO, REFORMA {i}"\n' if i % 3 else f'2002,{1000 + i},ACAO {i}\n'
        for i in range(50)
    )
    package = make_package(
        tmp_path, 'classificadores',
        {'acao': 'ano,cod,nome\n' + rows},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['acao']},
    )

    linktable.linktable_packages([package], name='orcamento')

    output = Package(tmp_path / 'datapackages' / 'orcamento' / 'datapackage.json')
    for resource in output.resources:
        assert resource.dialect.get_control('csv').delimiter == ','

    fact = output.get_resource('fact_classificadores_acao')
    assert [field.name for field in fact.schema.fields] == ['key_classificadores_acao']
    assert len(fact.read_rows()) == 50


# Output name and folder -------------------------------------------------------
@pytest.mark.parametrize('name', ['Orcamento', 'orcamento linktable', 'a/b'])
def test_linktable_packages_fails_on_invalid_name(tmp_path, caplog, name):
    """The name must be a valid data package name."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
    )

    with pytest.raises(SystemExit):
        linktable.linktable_packages([package], name=name)

    assert 'Invalid linktable name' in caplog.text


def test_linktable_packages_refuses_source_package_folder(tmp_path, caplog):
    """A name pointing to a source package folder stops the process, leaving its files untouched."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
        folder='datapackages/despesa',
    )
    before = (tmp_path / 'datapackages' / 'despesa' / 'datapackage.json').read_text()

    with pytest.raises(SystemExit):
        linktable.linktable_packages([package], name='despesa', descriptor=single(package))

    assert 'holds a source data package' in caplog.text
    assert (tmp_path / 'datapackages' / 'despesa' / 'datapackage.json').read_text() == before


def test_linktable_packages_regenerates_among_other_packages(tmp_path):
    """Without -d, datapackages/* also holds the generated package: it is skipped
    (no dpetl_linktable) and can be regenerated."""
    despesa = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
        folder='datapackages/despesa',
    )
    linktable.linktable_packages([despesa], name='orcamento')
    generated = Package(tmp_path / 'datapackages' / 'orcamento' / 'datapackage.json')

    linktable.linktable_packages([despesa, generated], name='orcamento')

    descriptor, _ = read_output(tmp_path, 'orcamento')
    assert [r['name'] for r in descriptor['resources']] == ['fact_despesa_execucao', 'linktable']


# Resources with the same name ------------------------------------------------
def test_linktable_packages_keeps_same_resource_of_different_packages_apart(tmp_path):
    """The same resource name in different packages becomes two fact tables, prefixed by package."""
    packages = [
        make_package(
            tmp_path, name,
            {'execucao': 'ano,vlr_valor\n2024,100\n'},
            dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
        )
        for name in ('despesa', 'receita')
    ]

    linktable.linktable_packages(packages, name='orcamento')

    _, files = read_output(tmp_path, 'orcamento')
    assert sorted(files) == [
        'fact_despesa_execucao.csv.gz',
        'fact_receita_execucao.csv.gz',
        'linktable.csv.gz',
    ]


def test_linktable_packages_stacks_same_package_in_different_years(tmp_path):
    """The same package and resource (e.g. different years) are stacked into one fact table."""
    packages = [
        make_package(
            tmp_path, 'dados_siafi',
            {'execucao': f'ano,orgao,vlr_empenhado\n{year},A,{value}\n'},
            dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
            folder=f'dados_siafi_{year}',
        )
        for year, value in ((2024, 100), (2025, 200))
    ]

    linktable.linktable_packages(packages, name='siafi')

    _, files = read_output(tmp_path, 'siafi')
    fact = files['fact_dados_siafi_execucao.csv.gz']
    assert fact.to_dict('list') == {
        'key_dados_siafi_execucao': ['2024|A', '2025|A'],
        'vlr_empenhado': ['100', '200'],
    }

    table = files['linktable.csv.gz']
    assert table['key_dados_siafi_execucao'].tolist() == ['2024|A', '2025|A']


def test_linktable_packages_fails_on_stacking_different_fields(tmp_path, caplog):
    """Stacked resources must share the same dimensions and facts."""
    packages = [
        make_package(
            tmp_path, 'dados_siafi',
            {'execucao': csv},
            dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao']},
            folder=f'dados_siafi_{year}',
        )
        for year, csv in (
            (2024, 'ano,orgao,vlr_empenhado\n2024,A,100\n'),
            (2025, 'ano,uo,vlr_empenhado\n2025,A,200\n'),
        )
    ]

    with pytest.raises(SystemExit):
        linktable.linktable_packages(packages, name='siafi')

    assert 'Resource execucao has different fields in packages named dados_siafi.' in caplog.text
    assert not (tmp_path / 'datapackages' / 'siafi').exists()


def test_linktable_packages_fails_without_schema(tmp_path, caplog):
    """A resource without schema fields (e.g. transform not run) stops the process."""
    folder = tmp_path / 'despesa'
    (folder / 'data').mkdir(parents=True)
    (folder / 'data' / 'execucao.csv').write_text('ano,vlr_empenhado\n2024,100\n')
    (folder / 'datapackage.json').write_text(json.dumps({
        'name': 'despesa',
        'resources': [{'name': 'execucao', 'path': 'data/execucao.csv'}],
        'dpetl_linktable': {'facts': ['vlr_*'], 'resource_list': ['execucao']},
    }))

    with pytest.raises(SystemExit):
        linktable.linktable_packages([Package(folder / 'datapackage.json')], name='orcamento')

    assert 'Resource execucao of package despesa has no schema fields.' in caplog.text
    assert not (tmp_path / 'datapackages').exists()


# Facts configuration ----------------------------------------------------------
def build_single(tmp_path, csv, dpetl_linktable):
    """Build the linktable of a single 'despesa' package and return its files."""
    package = make_package(tmp_path, 'despesa', {'execucao': csv}, dpetl_linktable=dpetl_linktable)
    linktable.linktable_packages([package], descriptor=single(package))
    _, files = read_output(tmp_path, 'despesa_linktable')
    return files


@pytest.mark.parametrize('dpetl_linktable, columns', [
    ({'facts': ['qtd_*'], 'resource_list': ['execucao']}, ['key_execucao', 'qtd_itens']),
    ({'facts': 'qtd_*', 'resource_list': ['execucao']}, ['key_execucao', 'qtd_itens']),
    ({'facts': ['qtd_*'], 'resource_list': [{'name': 'execucao', 'facts': ['vlr_*', 'total']}]},
     ['key_execucao', 'vlr_pago', 'total']),
    ({'facts': ['vlr_*'], 'resource_list': [{'name': 'execucao', 'facts': []}]}, ['key_execucao']),
])
def test_linktable_packages_facts(tmp_path, dpetl_linktable, columns):
    """Facts are set for the package and can be overridden per resource."""
    files = build_single(
        tmp_path, 'ano,vlr_pago,qtd_itens,total\n2024,100,3,7\n', dpetl_linktable,
    )

    assert list(files['fact_execucao.csv.gz'].columns) == columns


def test_linktable_packages_non_facts_are_dimensions(tmp_path):
    """Fields not matching the facts patterns become dimensions (key and linktable)."""
    files = build_single(
        tmp_path, 'ano,vlr_pago,qtd_itens\n2024,100,3\n',
        {'facts': ['qtd_*'], 'resource_list': ['execucao']},
    )

    assert files['fact_execucao.csv.gz']['key_execucao'].tolist() == ['2024|100']
    assert list(files['linktable.csv.gz'].columns) == ['key_execucao', 'ano', 'vlr_pago']


@pytest.mark.parametrize('resource_list', [
    ['execucao'],
    [{'name': 'execucao', 'facts': ['vlr_*']}],
])
def test_linktable_packages_requires_package_facts(tmp_path, caplog, resource_list):
    """Package facts are required, even when every resource sets its own."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_pago\n2024,100\n'},
        dpetl_linktable={'resource_list': resource_list},
    )

    with pytest.raises(SystemExit):
        linktable.linktable_packages([package], descriptor=single(package))

    assert 'Missing required field "facts" in "dpetl_linktable" for package despesa.' in caplog.text
    assert not (tmp_path / 'datapackages').exists()


def test_linktable_packages_fails_on_unknown_fact(tmp_path, caplog):
    """A fact given by name (no wildcard) that is not a field stops the process."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_pago\n2024,100\n'},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': [{'name': 'execucao', 'facts': ['vlr_*', 'totl']}]},
    )

    with pytest.raises(SystemExit):
        linktable.linktable_packages([package], descriptor=single(package))

    assert 'Facts not found in resource execucao of package despesa: totl.' in caplog.text
    assert not (tmp_path / 'datapackages').exists()


def test_linktable_packages_ignores_unmatched_fact_pattern(tmp_path):
    """A pattern matching no field is not an error (e.g. a package-wide default)."""
    files = build_single(
        tmp_path, 'ano,vlr_pago\n2024,100\n',
        {'facts': ['vlr_*', 'qtd_*'], 'resource_list': ['execucao']},
    )

    assert list(files['fact_execucao.csv.gz'].columns) == ['key_execucao', 'vlr_pago']


@pytest.mark.parametrize('csv, missing', [
    ('ano,orgao\n2024,A\n', 'facts'),
    ('vlr_pago\n100\n', 'dimensions'),
])
def test_linktable_packages_warns_without_facts_or_dimensions(tmp_path, caplog, csv, missing):
    """A resource without facts or without dimensions is built, with a warning."""
    build_single(tmp_path, csv, {'facts': ['vlr_*'], 'resource_list': ['execucao']})

    assert f'Resource execucao of package despesa has no {missing}.' in caplog.text


@pytest.mark.parametrize('dpetl_linktable', [
    {'facts': 10, 'resource_list': ['execucao']},
    {'facts': ['vlr_*', 1], 'resource_list': ['execucao']},
    {'facts': ['vlr_*'], 'resource_list': [{'name': 'execucao', 'facts': {'vlr': True}}]},
    {'facts': ['vlr_*'], 'resource_list': [{'facts': ['vlr_*']}]},
    {'facts': ['vlr_*'], 'resource_list': [['execucao']]},
])
def test_linktable_packages_fails_on_invalid_facts_config(tmp_path, dpetl_linktable):
    """Invalid facts or resource_list items stop the process."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_pago\n2024,100\n'},
        dpetl_linktable=dpetl_linktable,
    )

    with pytest.raises(SystemExit):
        linktable.linktable_packages([package], descriptor=single(package))

    assert not (tmp_path / 'datapackages').exists()


@pytest.mark.parametrize('facts_2025, stacked', [
    (['total'], True),
    (['vlr_*'], False),
])
def test_linktable_packages_stacks_with_facts_of_each_package(tmp_path, caplog, facts_2025, stacked):
    """Stacked resources are split by their own package facts: the same fields
    with different facts cannot be stacked."""
    packages = [
        make_package(
            tmp_path, 'dados_siafi',
            {'execucao': f'ano,total\n{year},100\n'},
            dpetl_linktable={
                'facts': facts,
                'resource_list': ['execucao'],
            },
            folder=f'dados_siafi_{year}',
        )
        for year, facts in ((2024, ['total']), (2025, facts_2025))
    ]

    if stacked:
        linktable.linktable_packages(packages, name='siafi')
        _, files = read_output(tmp_path, 'siafi')
        assert files['fact_dados_siafi_execucao.csv.gz']['total'].tolist() == ['100', '100']
    else:
        with pytest.raises(SystemExit):
            linktable.linktable_packages(packages, name='siafi')
        assert 'Stacked fact tables need the same dimensions and facts.' in caplog.text


# Package selection ------------------------------------------------------------
@pytest.mark.parametrize('dpetl_linktable', [None, False, {'enabled': False}])
def test_linktable_packages_skips_disabled_packages(tmp_path, dpetl_linktable):
    """Packages without dpetl_linktable (or with it disabled) are skipped and nothing is written."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable=dpetl_linktable,
    )

    linktable.linktable_packages([package], name='orcamento')

    assert not (tmp_path / 'datapackages').exists()


# Configuration errors ---------------------------------------------------------
@pytest.mark.parametrize('dpetl_linktable', [True, {'facts': ['vlr_*'], 'resource_list': []}])
def test_linktable_packages_requires_resource_list(tmp_path, dpetl_linktable):
    """An enabled package without resource_list stops the process."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable=dpetl_linktable,
    )

    with pytest.raises(SystemExit):
        linktable.linktable_packages([package], name='orcamento')

    assert not (tmp_path / 'datapackages').exists()


def test_linktable_packages_fails_on_unknown_resource(tmp_path, caplog):
    """A resource_list entry that does not exist in the package stops the process."""
    package = make_package(
        tmp_path, 'despesa',
        {'execucao': 'ano,vlr_empenhado\n2024,100\n'},
        dpetl_linktable={'facts': ['vlr_*'], 'resource_list': ['execucao', 'inexistente']},
    )

    with pytest.raises(SystemExit):
        linktable.linktable_packages([package], name='orcamento')

    assert 'Resources not found in package despesa: inexistente.' in caplog.text
    assert not (tmp_path / 'datapackages').exists()
