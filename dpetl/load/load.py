import os
import logging
from pathlib import Path
from frictionless import Package
from dotenv import load_dotenv, find_dotenv

from .github import repo_exists, create_repo, commit_files

logger = logging.getLogger(__name__)


def load_package(descriptor, **kwargs):
    """
    Load data and metadata from a datapackage into a GitHub repository.
    """

    # Get environment variables
    load_dotenv(find_dotenv(usecwd=True))
    token = os.environ.get('GH_TOKEN')
    owner = os.environ.get('GH_OWNER')

    if not all([token, owner]):
        logger.error(('Missing one of the required environment variables:'
                      'GH_TOKEN or GH_OWNER.'))
        raise SystemExit(1)

    # Prepare config, dataset version and repository paths
    org = kwargs.get('org', False)
    private = kwargs.get('private', False)

    package = Package(descriptor)
    datapackage = Path(descriptor)

    year = get_max_year(package)
    repo = f'{package.name}_{year}'

    logger.info(f'Processing {repo}.')

    # Ensure remote repository exists
    if not repo_exists(owner, repo, token):
        logger.info(f'Creating repository {repo}.')
        create_repo(owner, repo, token, private=private, org=org)

    # Prepare files to send
    files = {}
    for resource in package.resources:
        file = datapackage.parent / resource.path
        with open(file, 'rb') as f:
            files[resource.path] = f.read()

    files['datapackage.json'] = package.to_json().encode()

    # Commit all files in a single commit
    logger.info('Committing data package.')

    commit_files(owner, repo, token, files)


def get_max_year(package):
    """
    Extract the maximum 'ano' value across all data resources.
    """

    return max(row['ano']
               for resource in package.resources
               for row in resource.read_rows()
               if row.get('ano') is not None)
