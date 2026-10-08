# dpetl — Data package ETL

[![Release](https://img.shields.io/pypi/v/dpetl.svg)](https://pypi.python.org/pypi/dpetl)
![Coverage](coverage.svg)

The `dpetl` is a command-line interface (CLI) tool designed to run the three ETL phases (Extract, Transform, Load).

It is designed to work alongside the [Data Package standard specification](https://datapackage.org/).


## Installation

It requires Python 3.10 or more.

```bash
# Install:
pip install dpetl

poetry add dpetl

# Optional dependencies
pip install dpetl[github-app]

poetry install --extras github-app
```

To load data into Postgres (see [Loading to Postgres](#loading-to-postgres)), install with:

```bash
# using pip
pip install "dpetl[postgres]"

# using poetry
poetry add "dpetl[postgres]"
```

Extras can be combined, e.g. `dpetl[github-app,postgres]`.

## Usage

## Usage

Use `dpetl --help` to inspect the CLI.

```bash
dpetl extract    # download the data (modes: api, email, cli)
dpetl transform  # rename fields, anonymize values and export the files
dpetl load       # publish the data to a GitHub repository
```


## How it works

The CLI reads the Data Package descriptor:

- `datapackage.yaml` when running `extract` or `transform`

- `datapackage.json` when running `load` or `linktable`

Then it runs each phase on its resources, following the `dpetl_extract`, `dpetl_transform` and `dpetl_load` properties declared in it.

If you have **multiple data packages**, place them in a `datapackages/` folder (each in its own subdirectory) and dpetl will process all of them.

You can also **specify one or more descriptors** manually using the `-d` or `--descriptor` flag (it can be passed multiple times). This is useful when you want to test a specific configuration or process a file that is not in the default location.

```bash
# Single descriptor
dpetl transform -d configs/datapackage_payroll.yaml

# Multiple descriptors
dpetl extract -d datapackages/sales/datapackage.yaml -d datapackages/hr/datapackage.yaml
```

You can **skip a command entirely for a given package** by setting `enabled: false` under the corresponding `dpetl_extract`, `dpetl_transform` or `dpetl_load` key at the package level in the descriptor.

```yaml
# full form
dpetl_extract:
  enabled: false

# shorthand, equivalent to the above
dpetl_extract: false
```

Environment variables for email extraction, GitHub authentication, and proxy settings can be defined in a `.env` file in the current working directory — it is loaded automatically.

See the [Environment Variables](#environment-variables) section for the complete list of supported variables and their usage.


## `extract`

Runs the ETL extraction phase. Downloads data from external sources (API, email) and saves them locally as configured in the datapackage.

```bash
# Run extract using the default datapackage.yaml descriptor
dpetl extract

# Extract emails received today only
dpetl extract --today-email   # or -t

# Include package name in email subject search pattern
dpetl extract --add-package-name   # or -a

# Add a delay between resource extractions (in seconds)
dpetl extract --delay 5   # or -d 5
```

Each resource in the descriptor must declare an extraction `mode` (`email` or `api`) inside its `dpetl_extract` property (see [Example Data Package Configuration](#example-data-package-configuration)). If a resource is missing this property, the whole package extraction stops immediately.

### API Extractor

Reads the request settings from the resource's `sources` property:

- `method`: required (e.g. `get`, `post`).

- `path`: required. Treated as a **base URL**, not the full file URL.

  dpetl appends the file name from `resource.path` to it (e.g. `https://api.example.com` + `data/invoices.csv` → `https://api.example.com/invoices.csv`).

- `timeout`: optional, in seconds (defaults to 30).

- `params`, `headers`, `stream`: optional, passed directly to the request.

Once the URL is built, dpetl makes the request and saves the response to `resource.path`.

If the resource declares `extrapaths` (multiple files for the same resource), the same steps run once per path, reusing the same base URL.

### CLI Extractor

Executes local command-line commands to generate or fetch data for the resource.

Configure with `mode: cli` and a list of `arguments` under `dpetl_extract`:

- `arguments`: required. A list of shell commands to run sequentially.

Each command is executed in order. If a command fails, the error is logged and execution continues with the next command.

### Email Extractor

Connects to your IMAP server using environment variables (`EMAIL_USER`, `EMAIL_PWD`, `EMAIL_IMAP`), applying proxy settings (`HTTP_PROXY`/`HTTPS_PROXY`) if set.

It then searches for the **most recent** e-mail matching `criteria`:

- `subject`: if you don't set it in the datapackage (`criteria.subject`), it defaults to the resource name (or `{package_name}_{resource_name}` with `--add-package-name`).

- `date_gte`: if you don't set it in the datapackage (`criteria.date_gte`), it defaults to the most recent e-mail (no date filter). Passing `--today-email` sets it to today's date.

- any other filter supported by [imap-tools](https://pypi.org/project/imap-tools/#user-content--email-attributes) (sender, folder, etc.) can also be set.

Once a matching e-mail is found, its first attachment is saved to `resource.path`. If there is more than one attachment, the extra ones are saved next to it, named `{name}_1{ext}`, `{name}_2{ext}`, and so on.

If the resource declares `extrapaths` (multiple files for the same resource), the same search-and-save logic runs once per path.


## `transform`

Runs the ETL transformation phase. Applies column renaming, format conversion, and other transformations defined in the datapackage (see [Example Data Package Configuration](#example-data-package-configuration)).

```bash
# Run transform using the default datapackage.yaml descriptor
dpetl transform

# Generate a secret key for AES‑SIV anonymization
dpetl transform keygen
```

### Resource properties

Each resource can be exported using dpetl's built-in pipeline, an external command, or both. When both are used, the command runs after the pipeline, so it can further modify the file dpetl has already written.

After transformation, each resource becomes a single file, with updated `path`, `extrapaths` (removed), `scheme`, `format` and `compression` (if any) values, and inferred `stats`.

#### Output settings (for the built‑in pipeline)

These are read from the resource's dpetl_transform property:

- `path`: optional (defaults to `data`). Folder where the transformed file is saved.

- `format`: optional (defaults to `csv.gz`, a gzip-compressed CSV).

  Supported formats: `csv`, `txt`, `xlsx` — optionally followed by a compression, like `csv.gz`.

- `encoding`: optional (defaults to `utf-8`). Used for `csv`/`txt` files.

- `delimiter`: optional (defaults to `,`). Field separator used for `csv`/`txt` files.

- `package_linktable`: optional (defaults to `false`). If `true`, the resource takes part in the package's linktable (see [Package linktable](#package-linktable)).

#### `cli`

Runs shell commands as a complement to or replacement for the built‑in pipeline:

- `arguments`: list of commands, executed in order.

- `path`: optional (defaults to `dpetl_transform.path`). Directory where the command's output is expected.

- `pre_process`: optional (defaults to `true`). If `true`, the built‑in pipeline runs first and the command should (over)write that same file. If false, the built‑in pipeline is skipped and the command alone produces the output file.

The cli's output must be a file named after the resource (case‑insensitive match). Its `format`, `encoding` and `schema` are inferred directly from that file – not from the settings above.

### Field properties

Any field in the resource schema may define additional properties to modify its behaviour.

#### `target`

If a field defines a `target` property, the field is renamed to the specified target value. After transformation, the `target` property is removed.

#### `anonymize`

Fields can be anonymized during transformation by defining an `anonymize` property.

Supported `method` values:

- `sha256`: deterministic hash (first 16 hex chars) – requires no secret key.

- `aes_siv`: deterministic encryption (AES-SIV) – requires `ANONYMIZE_SECRET_KEY`.
  - `context`: optional **context tweak** – uses another field's value as a cryptographic context, so identical values in different contexts produce different tokens.
  - `annotation`: optional **surrogate annotation** – a human‑readable prefix prepended to the encrypted value.
  - `ANONYMIZE_SECRET_KEY`: to generate a secret key for AES‑SIV, use `dpetl transform keygen`

- `[pattern]`: mask pattern, e.g. `[###-###]` or `[###-###|####-####]`.
  - `#` preserves the original digit.
  - `*` masks the digit (replaces with `*`).
  - Other characters are literals.

You can also add a `filter` condition (a Python expression) to control which rows are anonymized.

### Package linktable

Builds a linktable **inside a single data package**, from the resources that set `package_linktable: true`. To build a linktable across several data packages, use the [`linktable`](#linktable) command instead.

For each of these resources, after its transformation:

- Fields starting with `vlr_` are **facts**; every other field is a **dimension**.

- A fact table `fact_<resource>.csv.gz` is written with the facts and a `key_<resource>` column, built by joining the dimension values with `|` (e.g. `2024|A`).

After all resources are processed, the distinct dimension rows of every resource are combined into `linktable.csv.gz`, with one `key_<resource>` column per resource. Dimensions with the same name in different resources share a single column.

Files are written to a `linktable` folder next to the first resource's file, and the linktable is added to the package as a resource named `linktable`.

> **Note:** `updated_at` timestamp is added to the package, and the updated descriptor is saved as a JSON file.


## `load`

Runs the ETL load phase. Uploads transformed data and the updated `datapackage.json` to a GitHub repository, creating a single commit with all files. Alternatively, the data can be loaded into Postgres while the `datapackage.json` is still committed to GitHub (see [Loading to Postgres](#loading-to-postgres)).

```bash
# Run load using the default datapackage.json descriptor
dpetl load
```

### Authentication

dpetl supports two authentication methods:

- **Personal Access Token (PAT):** set `GH_TOKEN`.

- **GitHub App:** set `GH_APP_ID` and `GH_APP_PRIVATE_KEY`. Optionally set `GH_APP_INSTALLATION_ID` (auto‑discovered if omitted).

GitHub App authentication requires the optional `github-app` extra (see [Installation](#installation)).

**Remember:** The GitHub App must have `Contents` read/write permissions. If the repository does not exist yet, also grant `Administration` read/write so dpetl can create it automatically.

### Configuration

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

### Loading to Postgres

With `target: postgres`, the data goes to a Postgres database and only the `datapackage.json` is committed to GitHub. It requires the `postgres` extra (see [Optional dependencies](#optional-dependencies)) and the `PG_URL` environment variable, e.g. `postgresql://user:password@host:5432/database`.

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


## `linktable`

Builds a linktable **across data packages** and loads it into a new GitHub repository named `linktable`, or into the Postgres schema `linktable` when the packages use `target: postgres`.

```bash
# Run linktable over ./datapackage.json or every datapackages/*/datapackage.json
dpetl linktable

# Run linktable over specific packages
dpetl -d datapackages/despesa/datapackage.json -d datapackages/receita/datapackage.json linktable
```

**Remember:** run `dpetl transform` before `dpetl linktable`. The command reads the transformed `datapackage.json` of each package, so field renames (`target`) and anonymization are already applied, and dimensions with the same name in different packages represent the same data. dpetl does not check whether `transform` was run or whether its output is up to date.

### Configuration

Each package opts in through the package-level `dpetl_linktable` property:

- `resource_list`: required. Names of the resources used to build the linktable.

- `enabled`: optional (defaults to `true`). Set it to `false` (or use the shorthand `dpetl_linktable: false`) to leave the package out.

Packages without `dpetl_linktable` are skipped.

```yaml
dpetl_linktable:
  resource_list: [execucao, empenho]
```

### How it works

- Each listed resource becomes a fact table `data/fact_<package>_<resource>.csv.gz`: fields starting with `vlr_` are **facts**, every other field is a **dimension**, and a `key_<package>_<resource>` column joins the dimension values with `|` (e.g. `2024|A`). The package prefix keeps resources with the same name in different packages apart.

- Resources with the same package **and** resource names — typically the same package in different years — are **stacked** into a single fact table. They must have the same dimensions and facts, and the year must be one of the dimensions (e.g. an `ano` field); otherwise rows from different years get the same key.

- The distinct dimension rows of every fact table are combined into `data/linktable.csv.gz`, with one `key_<package>_<resource>` column per fact table. **Dimensions with the same name in different packages share a single column** — this is what links the packages together.

- The fact tables, the linktable and a `datapackage.json` are published in a single commit, following the same steps as [`load`](#load).

The destination reuses the `owner`, `level`, `visibility` and `target` from the packages' `dpetl_load` property, so these values must be the same in every package.

The command stops with an error, before anything is published, when:

- a package enables `dpetl_linktable` without a `resource_list`;

- a resource in `resource_list` does not exist in the package;

- stacked resources (same package and resource names) have different dimensions or facts;

- the packages' `dpetl_load` settings point to different `owner`, `level`, `visibility` or `target`.


## Example Data Package Configuration

The following example shows a complete `datapackage.yaml` configuration.

Note that `dpetl_extract` and `dpetl_transform` are defined per resource, while `dpetl_load` is defined at the package level.

```yaml
resources:
  # Example 1: API extraction
  - name: invoices
    path: data/invoices.csv
    sources:   # Request settings
      - method: get   # required (e.g. get, post)
        path: https://api.example.com   # required
        timeout: 30   # optional (Defaults to 30 seconds)
        params: {}   # optional
        headers: {}   # optional
        stream: false   # optional (Defaults to false)
    dpetl_extract:
      mode: api

  # Example 2: Email extraction
  - name: payroll_from_email
    path: data/payroll.xlsx
    dpetl_extract:
      mode: email
      mailbox: INBOX   # optional (Defaults to INBOX)
      criteria:   # optional
        subject: "Payroll Report"   # optional (Defaults to resource name. See also the flag --add-package-name)
        from_: "finance@example.com"   # optional
        date_gte: 2024-01-01   # optional (See also the flag --today-email)

  # Example 3: CLI extraction
  - name: external_data
    path: data/external_data.csv
    dpetl_extract:
      mode: cli
      arguments:   # required. List of shell commands to run sequentially
        - curl -o data/external_data.csv https://api.example.com/export
        - python scripts/clean_data.py data/external_data.csv

  # Example 4: Static resource with column renaming
  - name: customers
    path: data/customers.csv
    schema:
      fields:
        - name: Name
          type: string
          target: customer_name
        - name: Region
          type: string
          target: customer_region
    dpetl_transform:
      format: csv.gz   # optional (Defaults to csv.gz)
      path: data/processed   # optional (Defaults to data)
      encoding: utf-8   # optional (Defaults to utf-8)
      delimiter: ';'   # optional (Defaults to ,)

# Example 5: Anonymization of sensitive fields
- name: employees
  path: data/employees.csv
  schema:
    fields:
      - name: employee_name
        type: string
        target: name_hashed
        anonymize:
          method: '[#***]'
      - name: tax_id
        type: string
        target: tax_id_encrypted
        anonymize:
          method: aes_siv
          context: department
          annotation: TAX:11
          filter: 'department == "Finance"'
      - name: phone
        type: string
        anonymize:
          method: '[###-***-####]'

# Load configuration (defined once per package)
dpetl_load:
  owner: github-username
  repo: my-data-repo
  level: user   # optional (Defaults to user)
  visibility: private   # optional (Defaults to private)
  target: github   # optional (Defaults to github). Use postgres to load data into Postgres
```


## Validation

To validate datapackage resources and schemas, dpetl uses `frictionless-py`.

Validation can occur in two stages:

- **Before processing**: validates the entire datapackage when `--validate-before` is used.

- **After processing**: validates each processed resource.

Validation behavior depends on the command:

- `extract`: validates each resource after download. `--validate-before` is not supported.

- `transform`: validates each resource after transformation. Use `--validate-before` to validate the entire datapackage before processing.

- `load` and `linktable`: validate before publishing only if `--validate-before` is used.

Use `--no-validate` to skip all validation.

Use `--no-stop` to continue processing resources even when validation errors are found.


## Global Flags

Flags that can be used with any command:

| Flag | Description |
|------|-------------|
| `--descriptor`, `-d` | Path to one or more datapackage descriptors (repeatable) |
| `--no-validate`, `-nv` | Skip datapackage validation |
| `--no-stop`, `-ns` | Continue even if validation fails (do not exit with error) |
| `--validate-before`, `-vb` | Run validation before processing (not supported for `extract`) |
| `--verbose` | Enable debug logging (also writes logs to `dpetl.debug.log`) |
| `--quiet`, `-q` | Suppress all logs except warnings and errors |
| `--version`, `-v` | Show version number and exit |
| `--help` | Show help message |


## Environment Variables

| Variable | Used By | Description |
|----------|---------|--------------|
| `EMAIL_USER` | extract (email mode) | Username for IMAP email connection |
| `EMAIL_PWD` | extract (email mode) | Password for IMAP email connection |
| `EMAIL_IMAP` | extract (email mode) | IMAP server address (e.g., imap.gmail.com) |
| `HTTP_PROXY` | extract (email mode) | Proxy settings for IMAP connections* |
| `ANONYMIZE_SECRET_KEY` | transform | Secret key for AES‑SIV anonymization |
| `GH_TOKEN` | load, linktable | GitHub Personal Access Token |
| `GH_APP_ID` | load, linktable | GitHub App ID |
| `GH_APP_PRIVATE_KEY` | load, linktable | GitHub App private key |
| `GH_APP_INSTALLATION_ID` | load, linktable | GitHub App installation ID (optional) |
| `PG_URL` | load, linktable (`target: postgres`) | Postgres connection URL, e.g. `postgresql://user:password@host:5432/database` |

All variables above can also be set in a `.env` file in the current directory instead of the shell environment.

**\* Proxy notes:** If your network requires a proxy, dpetl supports both uppercase and lowercase proxy environment variables. Use the format `http://user:pwd@host:port` when authentication is required.

## Documentation

Full documentation, with a page for each phase, the descriptor details and the API reference, at <https://splor-mg.github.io/dpetl/>.
