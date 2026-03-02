# dpetl — Data package ETL

`dpetl` is a command-line interface (CLI) tool designed to assist in running the three phases of the ETL (Extract, Transform, Load) process (although currently only the **extract** phase is implemented).

It is designed to work alongside the [Data Package standard specification](https://datapackage.org/).

## Installation

Install using pip:

```bash
pip install dpetl
```

## Usage

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

The CLI loads a Data Package descriptor (via the [`frictionless-py` Python package](https://framework.frictionlessdata.io/blog/2022/08-22-frictionless-framework-v5.html)) and iterates over its resources.

For each resource, `dpetl extract` comand reads the custom property:

```yaml
dptel_extract:
```

The key `mode` determines which extractor will run.

Currently available modes:

* `api`.
* `email`.

## Example Data Package Configuration

```yaml
# datapackage.yaml
resources:
  - name: invoices
    path: data/invoices.csv
    sources:
      - method: get
        path: https://api.example.com/invoices
		dptel_extract:
			mode: api

  - name: payroll_from_email
    path: data/payroll.xlsx
		dptel_extract:
			mode: email
			mailbox: INBOX  # optional (defaults to INBOX)
			criteria:
				subject: "Payroll Report" # optional (defaults to resource name)
```

## Extractors

### Email Extractor

* Connects to an IMAP server using environment variables:

  * `EMAIL_USER`.
  * `EMAIL_PWD`.
  * `EMAIL_IMAP`.

* Reads configuration from:

```yaml
dptel_extract:
  mode: email
  mailbox: INBOX        # optional (default: INBOX)
  criteria:             # optional
    subject: "Report"   # optional (default: resource.name)
    from_: "finance@example.com" # optional
    date_gte: 2024-01-01 #optional
```

Behavior:

* If `dptel_extract.mailbox` is not provided, `INBOX` is used.
* If `dptel_extract.criteria.subject` is not provided, it defaults to the resource `name`.
* The extractor searches for the most recent matching email.
* All e-mail attachments are saved to `resource.path`.

### API Extractor

* Reads `resource.sources`.
* Searches for a source containing a `method`.
* Downloads the file.
* Saves it to `resource.path`.


## Design Philosophy

The `dpetl` package follows a [convention over configuration](https://en.wikipedia.org/wiki/Convention_over_configuration) philosophy, treating the Data Package descriptor as the single source of truth for ETL process.

Each resource declares how it should be processed through structured metadata, enabling reproducible, declarative, and version-controlled data workflows.

The goal is to keep the CLI simple while allowing flexible strategies driven entirely by configuration rather than imperative scripting.
