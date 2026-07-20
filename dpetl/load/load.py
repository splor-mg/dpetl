import os
import logging
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

from dpetl.load import github
from dpetl.helpers import validate

logger = logging.getLogger(__name__)


def load_package(package, **kwargs):
    """
    Load data and metadata from a datapackage into a GitHub repository.
    """
    # Get environment variables
    load_dotenv(find_dotenv(usecwd=True))
    token = os.environ.get('GH_TOKEN')

    if not token:
        logger.error(('Missing required environment variables: GH_TOKEN.'))
        raise SystemExit(1)

    # Prepare config and repository paths
    dpetl = package.custom.get('dpetl_load', {})
    owner = dpetl.get('owner')
    repo   = dpetl.get('repo')
    level  = dpetl.get('level') or 'user'
    visibility = dpetl.get('visibility') or 'private'

    if repo and not owner:
        logger.error('Missing required field "owner" in "dpetl_load".')
        raise SystemExit(1)

    if level not in ('user', 'orgs'):
        logger.error('Field "level" in "dpetl_load" must be "user" or "orgs".')
        raise SystemExit(1)

    if visibility not in ('public', 'private'):
        logger.error('Field "visibility" in "dpetl_load" must be "public" or "private".')
        raise SystemExit(1)

    logger.info(f'Processing {repo or "local commit"}.')

    # Ensure remote repository exists
    if repo and not github.repo_exists(owner, repo, token):
        logger.info(f'Creating repository {repo}.')
        github.create_repo(owner, repo, token, level, visibility)

    # Prepare files to send
    files = {}
    for resource in package.resources:
        [resource.custom.pop(key, None) for key in ['dpetl_extract', 'dpetl_transform']]
        file = Path(package._basepath) / resource.path
        with open(file, 'rb') as f:
            files[resource.path] = f.read()

    [package.custom.pop(key, None) for key in ['dpetl_load']]
    files['datapackage.json'] = package.to_json().encode()

    validate.validate_datapackage(package, **kwargs)

    # Commit all files in a single commit
    logger.info('Committing data package.')

    if repo:
        github.commit_remote(owner, repo, token, files)
    else:
        github.commit_local(files)
