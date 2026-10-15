import os
import logging
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from frictionless import helpers

from dpetl.load import github, postgres
from dpetl.helpers import validate

logger = logging.getLogger('dpetl.load')

TARGETS = ('github', 'postgres')


def get_target_settings(package):
    """
    Extract and validate where the package data is loaded to.
    """
    dpetl = package.custom.get('dpetl_load', {})
    target = dpetl.get('target') or 'github'
    schema = dpetl.get('schema') or package.name

    if target not in TARGETS:
        logger.error(
            'Field "target" in "dpetl_load" must be one of: %s.',
            ', '.join(TARGETS)
        )
        raise SystemExit(1)

    return {
        'target': target,
        'schema': schema,
    }


def _get_token(owner):
    """
    Retrieve the authentication token from environment variables.
    """
    app_id = os.environ.get('GH_APP_ID')
    private_key = os.environ.get('GH_APP_PRIVATE_KEY')
    gh_token = os.environ.get('GH_TOKEN')

    if app_id and private_key:
        installation_id = os.environ.get('GH_APP_INSTALLATION_ID')
        logger.debug('Authenticating using GitHub App.')
        return github.get_installation_token(app_id, private_key, owner, installation_id)

    if gh_token:
        logger.debug('Authenticating using GitHub token.')
        return gh_token

    logger.error(
        'Missing required environment variables: '
        'GH_APP_ID + GH_APP_PRIVATE_KEY, or GH_TOKEN.'
    )
    raise SystemExit(1)


def read_files(package):
    """
    Read every resource file to be committed alongside the descriptor.
    """
    files = {}
    for resource in package.resources:
        file = Path(package._basepath) / resource.path
        with open(file, 'rb') as f:
            files[resource.path] = f.read()

    files['datapackage.json'] = package.to_json().encode()
    return files


def load_postgres(package, schema):
    """
    Load the data into Postgres. Only the descriptor, pointing to the
    tables, is committed.
    """
    descriptor = package.to_descriptor()
    descriptor['resources'] = postgres.load_tables(package, schema)

    return {'datapackage.json': helpers.to_json(descriptor).encode()}


def load_package(package, **kwargs):
    """
    Load data and metadata from a datapackage into a GitHub repository,
    or into Postgres with the descriptor committed to GitHub.
    """
    # Prepare config and repository paths
    settings = github.get_repo_settings(package)
    target = get_target_settings(package)

    load_dotenv(find_dotenv(usecwd=True))
    token = _get_token(settings['owner'])

    logger.debug(f'Processing {settings["repo"] or "local commit"}.')

    # Ensure remote repository exists
    if settings['repo'] and not github.repo_exists(token, **settings):
        github.create_repo(token, **settings)

    # Remove dpetl settings from the published descriptor
    for resource in package.resources:
        [resource.custom.pop(key, None) for key in ['dpetl_extract', 'dpetl_transform']]

    [package.custom.pop(key, None) for key in ['dpetl_extract', 'dpetl_transform', 'dpetl_load', 'dpetl_linktable']]

    validate.validate_datapackage(package, **kwargs)

    # Prepare files to send
    if target['target'] == 'postgres':
        files = load_postgres(package, target['schema'])
    else:
        files = read_files(package)

    # Commit all files in a single commit
    logger.debug('Committing data package.')

    deletions = github.get_deletions(token, files, **settings)

    if settings['repo']:
        github.commit_remote(token, files, deletions, **settings)
    else:
        github.commit_local(files, deletions)
