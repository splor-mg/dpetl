import logging
import tempfile
import pandas as pd
from pathlib import Path
from frictionless import Dialect, Package, Resource
from frictionless.formats import CsvControl

from dpetl.load import github, load
from dpetl.transform.linktable import build_key, create_linktable, split_fields

logger = logging.getLogger('dpetl.linktable')

REPO_NAME = 'linktable'


def get_resource_list(package):
    """
    Return the resources a package contributes to the linktable,
    or None when the package does not take part in it.
    """
    config = package.custom.get('dpetl_linktable') or {}
    enabled = config if isinstance(config, bool) else config.get('enabled', True)

    if not config or not enabled:
        logger.info('Skipping linktable for package %s.', package.name)
        return None

    resource_list = config.get('resource_list') if isinstance(config, dict) else None

    if not resource_list:
        logger.error(
            'Missing required field "resource_list" in "dpetl_linktable" '
            'for package %s.', package.name
        )
        raise SystemExit(1)

    missing = [name for name in resource_list if not package.has_resource(name)]

    if missing:
        logger.error(
            'Resources not found in package %s: %s.',
            package.name, ', '.join(missing)
        )
        raise SystemExit(1)

    return [package.get_resource(name) for name in resource_list]


def get_source_settings(package):
    """
    Return the dpetl_load settings a source package shares with the linktable.
    """
    repo = github.get_repo_settings(package)
    target = load.get_target_settings(package)

    return repo['owner'], repo['level'], repo['visibility'], target['target']


def get_load_settings(packages):
    """
    Build the destination settings from the source packages. All packages
    must share the same owner, level, visibility and target. With target
    postgres, the tables go to the schema named after the linktable package.
    """
    settings = set(map(get_source_settings, packages))

    if len(settings) > 1:
        logger.error(
            'Packages in the linktable must share the same "owner", '
            '"level", "visibility" and "target" in "dpetl_load".'
        )
        raise SystemExit(1)

    owner, level, visibility, target = settings.pop()

    if not owner:
        logger.error('Missing required field "owner" in "dpetl_load".')
        raise SystemExit(1)

    return {
        'owner': owner,
        'repo': REPO_NAME,
        'level': level,
        'visibility': visibility,
        'target': target,
    }


def group_fact_tables(selected):
    """
    Group the resources into fact tables named <package>_<resource>.
    Resources sharing both names (e.g. the same package in different years)
    are stacked into a single fact table.
    """
    groups = {}

    for package, resources in selected:
        for resource in resources:
            name = f'{package.name}_{resource.name}'
            dimensions, facts = split_fields(resource)

            group = groups.setdefault(name, {
                'dimensions': dimensions,
                'facts': facts,
                'frames': [],
            })

            # Stacked resources must share the same fields
            if (set(dimensions) != set(group['dimensions'])
                    or set(facts) != set(group['facts'])):
                logger.error(
                    'Resource %s has different fields in packages named %s. '
                    'Stacked fact tables need the same dimensions and facts.',
                    resource.name, package.name
                )
                raise SystemExit(1)

            group['frames'].append(resource.to_pandas())

    return groups


def write_fact_table(name, group, data_path):
    """
    Write the fact table and return its distinct dimension rows.
    """
    dimensions = group['dimensions']
    df = pd.concat(group['frames'], ignore_index=True)

    if len(group['frames']) > 1:
        logger.info(
            'Stacking %d resources into fact table %s.',
            len(group['frames']), name
        )

    fact = df[group['facts']].copy()
    fact.insert(0, f'key_{name}', build_key(df, dimensions))

    output_path = data_path / f'fact_{name}.csv.gz'
    logger.debug('Writing fact table %s to %s.', name, output_path)
    fact.to_csv(output_path, index=False)

    return df[dimensions].drop_duplicates()


def linktable_packages(packages, **kwargs):
    """
    Build fact tables and a linktable across data packages and load them
    into a GitHub repository.
    """
    selected = []
    for package in packages:
        resources = get_resource_list(package)
        if resources:
            selected.append((package, resources))

    if not selected:
        logger.warning('No package is configured with "dpetl_linktable".')
        return

    load_settings = get_load_settings([package for package, _ in selected])

    groups = group_fact_tables(selected)


    with tempfile.TemporaryDirectory() as tmp:
        basepath = Path(tmp)
        data_path = basepath / 'data'
        data_path.mkdir()

        package_dimensions = {}
        resource_dfs = []
        fact_resources = []

        for name, group in groups.items():
            resource_dfs.append(write_fact_table(name, group, data_path))
            package_dimensions[name] = group['dimensions']

            fact_resources.append(Resource(
                path=f'data/fact_{name}.csv.gz',
                basepath=str(basepath),
            ))

        logger.info('Building linktable.')
        linktable_resource = create_linktable(
            package_dimensions, resource_dfs, data_path, basepath
        )

        # Files are written by pandas with ',': sniffing could pick '|'
        # from the keys (e.g. fact tables with a single key column)
        resources = [*fact_resources, linktable_resource]
        for resource in resources:
            resource.dialect = Dialect(controls=[CsvControl(delimiter=',')])
            resource.infer(stats=True)


        package = Package(
            name=REPO_NAME,
            resources=resources,
            basepath=str(basepath),
        )
        package.custom['dpetl_load'] = load_settings

        load.load_package(package, **kwargs)
