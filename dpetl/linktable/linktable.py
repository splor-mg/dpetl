import logging
import tempfile
from pathlib import Path
from frictionless import Package, Resource

from dpetl.load import github, load
from dpetl.transform.linktable import create_fact_tables, create_linktable

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


def get_load_settings(packages):
    """
    Build the destination repository settings from the source packages.
    All packages must share the same owner, level and visibility.
    """
    settings = {
        (s['owner'], s['level'], s['visibility'])
        for s in map(github.get_repo_settings, packages)
    }

    if len(settings) > 1:
        logger.error(
            'Packages in the linktable must share the same "owner", '
            '"level" and "visibility" in "dpetl_load".'
        )
        raise SystemExit(1)

    owner, level, visibility = settings.pop()

    if not owner:
        logger.error('Missing required field "owner" in "dpetl_load".')
        raise SystemExit(1)

    return {
        'owner': owner,
        'repo': REPO_NAME,
        'level': level,
        'visibility': visibility,
    }


def linktable_packages(packages, **kwargs):
    """
    Build fact tables and a linktable across data packages and load them
    into a GitHub repository.
    """
    selected = {}
    for package in packages:
        resources = get_resource_list(package)
        if resources:
            selected[package.name] = (package, resources)

    if not selected:
        logger.warning('No package is configured with "dpetl_linktable".')
        return

    load_settings = get_load_settings(
        [package for package, _ in selected.values()]
    )

    with tempfile.TemporaryDirectory() as tmp:
        basepath = Path(tmp)
        data_path = basepath / 'data'

        package_dimensions = {}
        resource_dfs = []
        fact_resources = []
        sources = {}

        for package_name, (package, resources) in selected.items():
            logger.info('Building fact tables for package %s.', package_name)

            for resource in resources:
                # Resources with the same name would overwrite each other
                if resource.name in sources:
                    logger.error(
                        'Resource %s exists in packages %s and %s. '
                        'Resource names must be unique across the linktable.',
                        resource.name, sources[resource.name], package_name
                    )
                    raise SystemExit(1)
                sources[resource.name] = package_name

                dimensions, resource_df = create_fact_tables(resource, data_path)
                package_dimensions[resource.name] = dimensions
                resource_dfs.append(resource_df)

                fact_resources.append(Resource(
                    path=f'data/fact_{resource.name}.csv.gz',
                    basepath=str(basepath),
                ))

        logger.info('Building linktable.')
        linktable_resource = create_linktable(
            package_dimensions, resource_dfs, data_path, basepath
        )

        resources = [*fact_resources, linktable_resource]
        for resource in resources:
            resource.infer(stats=True)

        package = Package(
            name=REPO_NAME,
            resources=resources,
            basepath=str(basepath),
        )
        package.custom['dpetl_load'] = load_settings

        load.load_package(package, **kwargs)
