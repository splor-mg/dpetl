# Load

Runs the ETL load phase. Uploads transformed data and the updated `datapackage.json` to a GitHub repository, creating a single commit with all files. Alternatively, the data can be loaded into Postgres while the `datapackage.json` is still committed to GitHub (see [Loading to Postgres](#loading-to-postgres)).

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

- `target`: optional (defaults to `github`). Where the data is loaded: `github` or `postgres`.

- `schema`: optional (defaults to the package name). Postgres schema that receives the tables when `target` is `postgres`.

If `repo` is set and the repository doesn't exist, dpetl creates it automatically.

Before publishing, the `dpetl_extract`, `dpetl_transform`, `dpetl_load` and `dpetl_linktable` properties are removed from the descriptor.

A single commit publishes the transformed data and the updated `datapackage.json`, keeping the repository in sync with the current package definition.

## Loading to Postgres

With `target: postgres`, the data goes to a Postgres database and only the `datapackage.json` is committed to GitHub. It requires the `postgres` extra (see [Installation](index.md#installation)) and the `PG_URL` environment variable, e.g. `postgresql://user:password@host:5432/database`.

```yaml
dpetl_load:
  owner: github-username
  repo: my-data-repo
  level: user
  visibility: private
  target: postgres
  schema: my_schema   # optional (Defaults to the package name)
```

- Each resource becomes the table `<schema>.<resource name>`, with column types taken from the Table Schema (`integer` → `bigint`, `number` → `numeric`, `date` → `date`, `datetime` → `timestamp`; other types become `text`).

- Tables are recreated on every load, and tables of resources removed from the package are dropped. Views and other objects in the schema are kept.

- Everything runs in a single transaction: if any resource fails, the database keeps the previous version of all tables.

- Only delimited text resources (`csv`, `txt`, optionally compressed) can be loaded.

- In the committed `datapackage.json`, each resource points to its table using the frictionless SQL format, without credentials:

    ```json
    "path": "postgresql://host:5432/database",
    "dialect": {"sql": {"table": "execucao", "namespace": "my_schema"}}
    ```

    Since the host is published, prefer private repositories for packages loaded to Postgres.

The data is loaded before the descriptor is committed. If the GitHub commit fails, the database is already up to date and the descriptor is updated on the next successful load.

When a package already published on GitHub switches to `target: postgres`, its data files are removed from the repository on the next load (they remain in the Git history).

## Retries and errors

Requests to the GitHub API are retried up to 5 times on rate limits and temporary server errors. If they still fail, the load stops with an `HTTPError` and no commit is made.

## Example

The `dpetl_load` property is defined once, at the package level. See the [complete example](example.md).

```yaml
{% include "load.yaml" %}
```

See the [API reference](api/load.md).
