# dpetl — Data package ETL

[![Release](https://img.shields.io/pypi/v/dpetl.svg)](https://pypi.python.org/pypi/dpetl)

The `dpetl` is a command-line interface (CLI) tool designed to run the three ETL phases (Extract, Transform, Load)[^1]

[^1]: Although currently only the **Extract** phase is implemented.

It is designed to work alongside the [Data Package standard specification](https://datapackage.org/).

## Installation

It requires Python 3.10 or more.
Install:

```bash
# using pip
pip install dpetl

# using poetry
poetry add dpetl
```

## Usage

Active your virtual environment!

Use the `--help` flag to inspect the CLI documentation:

```bash
dpetl --help
```

Currently, only the `extract` command is available:

```bash
# Run extract using the default datapackage.yaml descriptor
dpetl extract

# Specify a descriptor explicitly
dpetl extract -d path/to/datapackage.yaml
# or
dpetl extract --descriptor path/to/datapackage.yaml
```

## How It Works

The CLI loads Data Package descriptor(s) (via the [`frictionless-py` Python package](https://framework.frictionlessdata.io/blog/2022/08-22-frictionless-framework-v5.html)) and iterates over its resources.

A `.toml` file could also be provided as a descriptor (using the `-d` flag) to run the command(s) recursively.
Please create a `.toml` file following the below pattern:

```toml
title = 'dados_orcamentarios'

[datapackages] # required

[datapackages.dados_siafi]
path = 'datapackages/dados_siafi/datapackage.yaml' # descriptor required via path property

[datapackages.dados_sisor]
path = 'datapackages/dados_sisor/datapackage.yaml' # descriptor required via path property
```

For each resource found, `dpetl extract` command reads its `dpetl_extract` custom property:
The key `mode` determines which extractor will run.
Currently, available modes are:

- `api`.
- `email`.

## Example Data Package Configuration

```yaml
# datapackage.yaml
resources:
  - name: invoices
    path: data/invoices.csv
    sources:
      - method: get
        path: https://api.example.com/invoices
    dpetl_extract:
      mode: api

  - name: payroll_from_email
    path: data/payroll.xlsx
    dpetl_extract:
      mode: email
      mailbox: INBOX  # optional (Defaults to INBOX)
      criteria:
        subject: "Payroll Report" # optional (Defaults to resource name. See also the flag --add-package-name)
```

## Extractors

### Email Extractor

- Connects to an IMAP server using environment variables:

  - `EMAIL_USER`.
  - `EMAIL_PWD`.
  - `EMAIL_IMAP`.
  - `HTTP_PROXY`[^2].

[^2]: Just in case you're running the command behind a corporate network that demands proxy configuration. The `HTTP_PROXY`, `HTTPS_PROXY`, `http_proxy` and `https_proxy` environment variables are equally acceptable. See [this Issue's comment](https://github.com/splor-mg/dpetl/issues/18#issuecomment-3986578696) to understand why maybe you'll have to add authentication (`http://<user>:<pwd>@<host>:<port>`) on PROXY address.

- Reads configuration from:

```yaml
dpetl_extract:
  mode: email
  mailbox: INBOX        # optional (Defaults to INBOX)
  criteria:             # optional
    subject: "Report"   # optional (Defaults to resource name. See also the flag --add-package-name)
    from_: "finance@example.com" # optional
    date_gte: 2024-01-01 #optional (See also the flag --today-email)
```

Behavior:

- If `dpetl_extract.mailbox` is not provided, `INBOX` is used.
- If `dpetl_extract.criteria.subject` is not provided, it defaults to the resource name.
- If the flag `--add-package-name` is provided the e-mail subject pattern will be `{package_name}_{resource_name}` instead of just resource name.
- If the flag `--today-email` is provided the date when the command runs will be used in the to search criteria.
- The extractor searches for the most recent matching e-mail.
- All e-mail attachments are saved to `resource.path`.

### API Extractor

- Reads `resource.sources`.
- Searches for a source containing a `method`.
- Downloads the file.
- Saves it to `resource.path`.


## Design Philosophy

The `dpetl` package follows a [convention over configuration](https://en.wikipedia.org/wiki/Convention_over_configuration) philosophy, treating the Data Package descriptor as the single source of truth for ETL process.

Each resource declares how it should be processed through structured metadata, enabling reproducible, declarative, and version-controlled data workflows.

The goal is to keep the CLI simple while allowing flexible strategies driven entirely by configuration rather than imperative scripting.
