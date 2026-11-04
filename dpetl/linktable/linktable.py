import re
import json
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime
from frictionless import Dialect, Package, Resource
from frictionless.formats import CsvControl

logger = logging.getLogger('dpetl.linktable')

OUTPUT_PATH = Path('datapackages')

# Frictionless package name pattern
NAME_PATTERN = re.compile(r'^[a-z0-9._-]+$')


def split_fields(resource):
    """
    Split the resource fields into dimensions and facts (fields starting
    with vlr_).
    """
    names = [field.name for field in resource.schema.fields]
    dimensions = [name for name in names if not name.startswith('vlr_')]
    facts = [name for name in names if name.startswith('vlr_')]
    return dimensions, facts


def build_key(df, dimensions):
    """
    Build the linktable key by joining the dimension values with '|'.
    """
    return (
        df[dimensions]
        .astype('string')
        .fillna('')
        .agg('|'.join, axis=1)
    )


def create_linktable(package_dimensions, resource_dfs, linktable_path, basepath):
    """
    Combine the distinct dimension rows of every fact table into the
    linktable, with one key column per fact table.
    """
    combined_df = pd.concat(resource_dfs, ignore_index=True)

    for resource_name, dimensions in package_dimensions.items():
        logger.debug('Adding resource %s key to linktable.', resource_name)
        key = build_key(combined_df, dimensions)
        combined_df.insert(0, f'key_{resource_name}', key)

    output_path = linktable_path / 'linktable.csv.gz'
    logger.debug('Writing linktable to %s.', output_path)
    combined_df.to_csv(output_path, index=False)

    return Resource(
        name='linktable',
        path=str(output_path.relative_to(basepath)),
        basepath=str(basepath),
        scheme='file',
        format='csv',
        encoding='utf-8',
    )


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


def group_fact_tables(selected, prefix=True):
    """
    Group the resources into fact tables named <package>_<resource>, or
    just <resource> without prefix (a single package). Resources sharing
    both names (e.g. the same package in different years) are stacked into
    a single fact table.
    """
    groups = {}

    for package, resources in selected:
        for resource in resources:
            name = (f'{package.name}_{resource.name}' if prefix
                    else resource.name)
            dimensions, facts = split_fields(resource)

            if not dimensions and not facts:
                logger.error(
                    'Resource %s of package %s has no schema fields. '
                    'Run "dpetl transform" before "dpetl linktable".',
                    resource.name, package.name
                )
                raise SystemExit(1)

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




def get_output_name(packages, name=None, single=False):
    """
    Resolve the name of the linktable package. Across data packages it must
    be given with --name; for a single package it defaults to
    <package>_linktable.
    """
    if not name and single:
        name = f'{packages[0].name}_linktable'

    if not name:
        logger.error(
            'Missing "--name" to build a linktable across data packages.'
        )
        raise SystemExit(1)

    if not NAME_PATTERN.match(name):
        logger.error(
            'Invalid linktable name "%s": use only lowercase letters, '
            'numbers, ".", "-" and "_".', name
        )
        raise SystemExit(1)

    return name


def get_output_folder(name, packages):
    """
    Return the folder of the linktable package, refusing the folder of a
    source package so its files are never overwritten.
    """
    folder = OUTPUT_PATH / name
    sources = {Path(package.basepath).resolve() for package in packages}

    if folder.resolve() in sources or (folder / 'datapackage.yaml').exists():
        logger.error(
            'Folder %s holds a source data package. Choose another "--name".',
            folder
        )
        raise SystemExit(1)

    return folder


def read_metadata(folder):
    """
    Return the metadata of a previously generated descriptor (e.g. the
    dpetl_load set by the user), so regenerating the package keeps it.
    """
    path = folder / 'datapackage.json'

    if not path.exists():
        return {}

    metadata = json.loads(path.read_text())
    metadata.pop('resources', None)
    return metadata


def write_descriptor(folder, name, resources):
    """
    Save the linktable package descriptor, keeping the metadata of the
    previous one.
    """
    metadata = read_metadata(folder)
    path = folder / 'datapackage.json'

    if 'dpetl_load' not in metadata:
        logger.warning('Set "dpetl_load" in %s before running load.', path)

    package = Package(name=name, resources=resources, basepath=str(folder))
    descriptor = {
        **metadata,
        **package.to_dict(),
        'updated_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
    }

    path.write_text(json.dumps(descriptor, indent=2, ensure_ascii=False))


def linktable_packages(packages, name=None, descriptor=None, **kwargs):
    """
    Build fact tables and a linktable as a new data package in
    datapackages/<name>, published later by load. A single -d builds it
    from that package; otherwise from every package with dpetl_linktable.
    """
    single = descriptor is not None and len(descriptor) == 1

    selected = []
    for package in packages:
        resources = get_resource_list(package)
        if resources:
            selected.append((package, resources))

    if not selected:
        logger.warning('No package is configured with "dpetl_linktable".')
        return

    name = get_output_name(packages, name, single)
    folder = get_output_folder(name, [package for package, _ in selected])

    groups = group_fact_tables(selected, prefix=not single)

    # Remove the files of a previous run, so no stale fact table is left
    data_path = folder / 'data'
    data_path.mkdir(parents=True, exist_ok=True)
    for path in [*data_path.glob('fact_*.csv.gz'),
                 data_path / 'linktable.csv.gz']:
        path.unlink(missing_ok=True)

    package_dimensions = {}
    resource_dfs = []
    resources = []

    for group_name, group in groups.items():
        resource_dfs.append(write_fact_table(group_name, group, data_path))
        package_dimensions[group_name] = group['dimensions']

        resources.append(Resource(
            path=f'data/fact_{group_name}.csv.gz',
            basepath=str(folder),
        ))

    logger.info('Building linktable.')
    resources.append(create_linktable(
        package_dimensions, resource_dfs, data_path, folder
    ))

    # Files are written by pandas with ',': sniffing could pick '|'
    # from the keys (e.g. fact tables with a single key column)
    for resource in resources:
        resource.dialect = Dialect(controls=[CsvControl(delimiter=',')])
        resource.infer(stats=True)

    write_descriptor(folder, name, resources)
    logger.info('Linktable package %s saved to %s.', name, folder)
