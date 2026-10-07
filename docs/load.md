# Load

Runs the ETL load phase. Uploads transformed data and the updated `datapackage.json` to a GitHub repository, creating a single commit with all files.

```bash
# Run load using the default datapackage.json descriptor
dpetl load
```

## Authentication

dpetl supports two authentication methods:

- **Personal Access Token (PAT):** set `GH_TOKEN`.

- **GitHub App:** set `GH_APP_ID` and `GH_APP_PRIVATE_KEY`. Optionally set `GH_APP_INSTALLATION_ID` (auto‑discovered if omitted).

GitHub App authentication requires the optional `github-app` extra (see [Installation](index.md#installation)).

**Remember:** The GitHub App must have `Contents` read/write permissions. If the repository does not exist yet, also grant `Administration` read/write so dpetl can create it automatically.

## Configuration

Reads its settings from the package's `dpetl_load` property:

- `repo`: optional. Name of the target repository (defaults to the current repository).

- `owner`: required if `repo` is set. GitHub user or organization name.

- `level`: optional (defaults to `user`). Use `orgs` to target a GitHub organization instead of a user account.

- `visibility`: optional (defaults to `private`). Use `public` for a public repository.

If `repo` is set and the repository doesn't exist, dpetl creates it automatically.

Before publishing, the `dpetl_extract`, `dpetl_transform` and `dpetl_load` properties are removed from the descriptor.

A single commit publishes the transformed data and the updated `datapackage.json`, keeping the repository in sync with the current package definition.

## Retries and errors

Requests to the GitHub API are retried up to 5 times on rate limits and temporary server errors. If they still fail, the load stops with an `HTTPError` and no commit is made.

## Example

The `dpetl_load` property is defined once, at the package level. See the [complete example](example.md).

```yaml
{% include "load.yaml" %}
```

See the [API reference](api/load.md).
