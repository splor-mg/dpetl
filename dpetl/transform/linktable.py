import logging
import pandas as pd
from frictionless import Resource

logger = logging.getLogger(__name__)


def create_fact_tables(resource, linktable_path):

    # Get dimensions and facts
    dimensions = [
        field.name
        for field in resource.schema.fields
        if not field.name.startswith('vlr_')
    ]

    facts = [
        field.name
        for field in resource.schema.fields
        if field.name.startswith('vlr_')
    ]

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
    key = (
        df[dimensions]
        .astype('string')
        .fillna('')
        .agg('|'.join, axis=1)
    )

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

        key = (
            combined_df[dimensions]
            .astype('string')
            .fillna('')
            .agg('|'.join, axis=1)
        )

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
    type='table',
    path=str(output_path.relative_to(basepath)),
    basepath=str(basepath),
    scheme='file',
    format='csv',
    encoding='utf-8'
    )

    return linktable_resource
