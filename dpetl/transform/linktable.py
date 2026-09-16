import pandas as pd
from frictionless import Resource

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
    print(f'Processing {resource.name}')
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

    print(f'Writing {resource.name} to {output_path}')

    df.to_csv(
        output_path,
        index=False
    )


    return dimensions, resource_dfs


def create_linktable(package_dimensions, resource_dfs, linktable_path):
    # create a combined dataframe with all the dimentions from all the resources, dropping duplicates
    combined_df = pd.concat(
        resource_dfs,
        ignore_index=True
    )

    # Create key
    for resource_name, dimensions in package_dimensions.items():
        print(f'Writing {resource_name} to linktable')

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
    combined_df.to_csv(
        output_path,
        index=False
        sep=';'
    )

    linktable_resource = Resource(
    name='linktable',
    type='table',
    path=str(output_path),
    scheme='file',
    format='csv',
    encoding='utf-8',
    dialect={
        'delimiter': ';'
    }
    )

    return linktable_resource
