import logging
import pandas as pd
from frictionless import Resource

logger = logging.getLogger(__name__)


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


def create_fact_tables(resource, linktable_path):

    # Get dimensions and facts
    dimensions, facts = split_fields(resource)

    # Create linktable directory if it doen´t exists
    linktable_path.mkdir(
        parents=True,
        exist_ok=True
    )

    # Read the resource as a pandas DataFrame
    logger.debug(
        'Creating fact table for resource %s.',
        resource.name
    )
    df = resource.to_pandas()

    # Keep only dimensions for the linktable
    resource_df = (
        df.copy()
        .drop(columns=facts)
        .drop_duplicates()
    )

    # Create key
    key = build_key(df, dimensions)

    # Remove dimensions and insert key in fact tables
    df = df.drop(columns=dimensions)
    df.insert(0, f'key_{resource.name}', key)

    # Rewrite fact table
    output_path = linktable_path / f'fact_{resource.name}.csv.gz'

    logger.debug(
        'Writing fact table for resource %s to %s.',
        resource.name,
        output_path
    )

    df.to_csv(
        output_path,
        index=False
    )


    return dimensions, resource_df


def create_linktable(package_dimensions, resource_dfs, linktable_path, basepath):
    # create a combined dataframe with all the dimentions from all the resources, dropping duplicates
    combined_df = pd.concat(
        resource_dfs,
        ignore_index=True
    )

    # Create key
    for resource_name, dimensions in package_dimensions.items():
        logger.debug(
            'Adding resource %s key to linktable.',
            resource_name
        )

        key = build_key(combined_df, dimensions)

        combined_df.insert(
            0,
            f'key_{resource_name}',
            key
        )

    output_path = linktable_path / 'linktable.csv.gz'

    # Write linktable
    logger.debug(
        'Writing linktable to %s.',
        output_path
    )
    combined_df.to_csv(
        output_path,
        index=False
    )

    linktable_resource = Resource(
    name='linktable',
    path=str(output_path.relative_to(basepath)),
    basepath=str(basepath),
    scheme='file',
    format='csv',
    encoding='utf-8'
    )

    return linktable_resource
