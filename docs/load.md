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

- `lfs`: optional. Sends large data files to Git LFS (see [Large files with Git LFS](#large-files-with-git-lfs)).

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

## Large files with Git LFS

GitHub rejects files larger than 100 MB. With `lfs`, data files larger than a threshold are sent to [Git LFS](https://git-lfs.com/) and only their LFS pointers are committed. It works for both remote (`repo` set) and local commits, and doesn't require `git-lfs` installed where dpetl runs.

```yaml
dpetl_load:
  owner: github-username
  repo: my-data-repo
  lfs:
    threshold: 50   # optional (Defaults to 50). Size in MB above which a file goes to LFS
    patterns: [data/*.csv.gz, data-raw/*.csv.gz]   # optional (Defaults to any data file)
    url: https://lfs.example.com/{owner}/{repo}   # optional (Defaults to the GitHub LFS storage)
```

`lfs: true` enables it with the defaults.

- `threshold`: files larger than this size (in MB) go to LFS. Use `0` to send every file matching `patterns`.

- `patterns`: only resource paths matching one of these patterns go to LFS. `*` doesn't cross folders (`data/*.csv.gz` doesn't match `data/2024/x.csv.gz`); use `**` for that.

- `url`: endpoint of your own LFS server (e.g. [Giftless](https://github.com/datopian/giftless) or [rudolfs](https://github.com/jasonwhite/rudolfs)). `{owner}` and `{repo}` are replaced by the repository owner and name (taken from the `origin` remote for local commits). Without `url`, files go to the GitHub LFS storage of the repository, subject to GitHub's LFS storage and bandwidth quotas.

Authentication:

- **GitHub LFS storage:** uses the same `GH_TOKEN` or GitHub App as the load. No extra permission is needed beyond `Contents` read/write.

- **Own server:** set `LFS_USERNAME` and `LFS_PASSWORD` (Basic authentication; for Giftless JWT tokens, use `_jwt` as the username and the token as the password). Without them, the server is used anonymously.

On each load, dpetl:

- uploads the files through the LFS batch API, skipping files the server already stores;

- commits the LFS pointers in place of the files. On local commits the working tree keeps the data files and `git push` skips the `git-lfs` pre-push hook, since the files are already on the server;

- keeps a block of `filter=lfs` rules, one per LFS file, in `.gitattributes`, between `# BEGIN dpetl lfs` and `# END dpetl lfs`. Rules outside the block are kept;

- with `url`, commits a `.lfsconfig` pointing to the server, so clones download the files from it.

The `datapackage.json` keeps the relative resource paths. They are valid in a clone with `git-lfs` installed, but reading a resource straight from GitHub (e.g. a `raw.githubusercontent.com` URL) returns the pointer instead of the data.

Without `lfs`, or when a large file doesn't match `patterns`, the load stops before committing if a file exceeds 100 MB.

If `lfs` is removed later, remove the dpetl block from `.gitattributes` (and the `.lfsconfig`) by hand.

!!! warning "GitHub LFS quotas and billing"

    Without `url`, files go to the GitHub LFS storage, which has a free quota per account (10 GiB of storage and 10 GiB of bandwidth on the free plans). Keep in mind that:

    - LFS stores files by content: every load with updated data adds a new version to the storage, and old versions stay there, counting toward the quota. Individual LFS objects can't be deleted; only deleting the repository (or contacting GitHub support) frees the space.
    - Downloads by anyone, including clones of public repositories, count toward the owner's bandwidth.
    - With a payment method, usage above the quota is billed automatically unless a budget limits it (a $0 budget blocks LFS for the rest of the month instead of billing).
    - Without a payment method, usage is blocked when the quota runs out: clones get only the pointers, new files can't be uploaded (the load fails) and, once the bandwidth is used up, LFS is disabled until the next month.

    Check the current quotas and prices in [GitHub's Git LFS billing documentation](https://docs.github.com/en/billing/concepts/product-billing/git-lfs). For large or frequently updated files, consider your own LFS server (`url`).

## Retries and errors

Requests to the GitHub API are retried up to 5 times on rate limits and temporary server errors. If they still fail, the load stops with an `HTTPError` and no commit is made.

## Example

The `dpetl_load` property is defined once, at the package level. See the [complete example](example.md).

```yaml
{% include "load.yaml" %}
```

See the [API reference](api/load.md).
