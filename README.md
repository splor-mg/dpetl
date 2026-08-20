# dpetl — Data package ETL

[![Release](https://img.shields.io/pypi/v/dpetl.svg)](https://pypi.python.org/pypi/dpetl)
![Coverage](coverage.svg)

The `dpetl` is a command-line interface (CLI) tool designed to run the three ETL phases (Extract, Transform, Load).

It is designed to work alongside the [Data Package standard specification](https://datapackage.org/).


## Installation

It requires Python 3.10 or more. Install:

```bash
# using pip
pip install dpetl

# using poetry
poetry add dpetl
```

### Optional dependencies

For GitHub App authentication, install with:

```bash
# using pip
pip install dpetl[github-app]

# using poetry
poetry install --extras github-app
```

## Usage

Activate your virtual environment!

Use the `--help` flag to inspect the CLI documentation:

```bash
dpetl --help
```


## How It Works

The CLI loads Data Package descriptor(s) (via the `frictionless-py` Python package) and iterates over its resources.

By default, the CLI looks for:

- `datapackage.yaml` when running `extract` or `transform`

- `datapackage.json` when running `load`

If you have **multiple data packages**, place them in a `datapackages/` folder (each in its own subdirectory) and dpetl will process all of them.

You can also **specify one or more descriptors** manually using the `-d` or `--descriptor` flag (it can be passed multiple times). This is useful when you want to test a specific configuration or process a file that is not in the default location.

```bash
# Single descriptor
dpetl transform -d configs/datapackage_payroll.yaml

# Multiple descriptors
dpetl extract -d datapackages/sales/datapackage.yaml -d datapackages/hr/datapackage.yaml
```

Environment variables for email extraction, GitHub authentication, and proxy settings can be defined in a `.env` file in the current working directory — it is loaded automatically.

See the [Environment Variables](#environment-variables) section for the complete list of supported variables and their usage.


## `extract`

Runs the ETL extraction phase. Downloads data from external sources (API, email) and saves them locally as configured in the datapackage.

```bash
# Run extract using the default datapackage.yaml descriptor
dpetl extract

# Extract emails received today only
dpetl extract --today-email

# Include package name in email subject search pattern
dpetl extract --add-package-name
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

Reads the transformation settings from the resource's `dpetl_transform` property:

- `path`: optional (defaults to `data`). Folder where the transformed file is saved.

- `format`: optional (defaults to `csv.gz`, a gzip-compressed CSV).

  Supported formats: `csv`, `txt`, `xlsx` — optionally followed by a compression, like `csv.gz`.

- `encoding`: optional (defaults to `utf-8`). Used for `csv`/`txt` files.

- `delimiter`: optional (defaults to `,`). Field separator used for `csv`/`txt` files.

Once all resources are transformed, each resource is converted to a single file, with updated `path`, `extrapaths` (removed), `scheme`, `format` and `compression` (if any) values, and inferred `stats`.

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

- `[pattern]`: mask pattern, e.g. `[###-###]` or `[###-###|####-####]`.
  - `#` preserves the original digit.
  - `*` masks the digit (replaces with `*`).
  - Other characters are literals.

To generate a secret key for AES‑SIV, use: `dpetl transform keygen`

After transformation, any `anonymize` properties are removed from the field metadata.

> **Note:** `updated_at` timestamp is added to the package, and the updated descriptor is saved as a JSON file.


## `load`

Runs the ETL load phase. Uploads transformed data and the updated `datapackage.json` to a GitHub repository, creating a single commit with all files.

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

If `repo` is set and the repository doesn't exist, dpetl creates it automatically.

Before publishing, the `dpetl_extract`, `dpetl_transform` and `dpetl_load` properties are removed from the descriptor.

The transformed data folder and the package descriptor, exported as `datapackage.json`, are published in a single commit.


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
  - name: employees
    path: data/employees.csv
    schema:
      fields:
        - name: Name
          type: string
          target: employee_name
        - name: Department
          type: string
          target: employee_department
    dpetl_transform:
      format: csv.gz   # optional (Defaults to csv.gz)
      path: data/processed   # optional (Defaults to data)
      encoding: utf-8   # optional (Defaults to utf-8)
      delimiter: ';'   # optional (Defaults to ,)

# Example 5: Anonymization of sensitive fields
- name: customers
  path: data/customers.csv
  schema:
    fields:
      - name: name
        type: string
        target: customer_name
        custom:
          anonymize:
            method: '[#***]'
      - name: cpf
        type: string
        custom:
          anonymize:
            method: aes_siv
            context: ano
            annotation: CPF:11|CNPJ:14
      - name: phone
        type: string
        custom:
          anonymize:
            method: '[###-***-####]'

# Load configuration (defined once per package)
dpetl_load:
  owner: github-username
  repo: my-data-repo
  level: user   # optional (Defaults to user)
  visibility: private   # optional (Defaults to private)
```


## Validation

To validate datapackage resources and schemas, dpetl uses `frictionless-py`.

Validation can occur in two stages:

- **Before processing**: validates the entire datapackage when `--validate-before` is used.

- **After processing**: validates each processed resource.

Validation behavior depends on the command:

- `extract`: validates each resource after download. `--validate-before` is not supported.

- `transform`: validates each resource after transformation. Use `--validate-before` to validate the entire datapackage before processing.

- `load`: validates before publishing only if `--validate-before` is used.

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
| `GH_TOKEN` | load | GitHub Personal Access Token |
| `GH_APP_ID` | load | GitHub App ID |
| `GH_APP_PRIVATE_KEY` | load | GitHub App private key |
| `GH_APP_INSTALLATION_ID` | load | GitHub App installation ID (optional) |

All variables above can also be set in a `.env` file in the current directory instead of the shell environment.

**\* Proxy notes:** If your network requires a proxy, dpetl supports both uppercase and lowercase proxy environment variables. Use the format `http://user:pwd@host:port` when authentication is required.


## Design Philosophy

The `dpetl` package follows a [convention over configuration](https://en.wikipedia.org/wiki/Convention_over_configuration) philosophy, treating the Data Package descriptor as the single source of truth for ETL process.

Each resource declares how it should be processed through structured metadata, enabling reproducible, declarative, and version-controlled data workflows.

The goal is to keep the CLI simple while allowing flexible strategies driven entirely by configuration rather than imperative scripting.
