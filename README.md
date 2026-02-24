# dpetl — simple ETL CLI using Frictionless

The `dpetl` is a [command-line interface](https://en.wikipedia.org/wiki/Command-line_interface) tool to assist running all the three phases of the [ETL](https://en.wikipedia.org/wiki/Extract,_transform,_load) process (although currently only the extract is implemented).
It was designing to work alongside the [Data Package standard specification](https://datapackage.org/).

### Installation

Install it using pip:

```bash
pip install dpetl
```

### Usage

Use the `--help` flag to read the CLI documentation on the terminal:

```bash
dpetl --help
```

As said, only the `extract` command is implemented:

```bash
# Run extract using the default datapackage.yaml descriptor
dpetl extract

# Or infor its path explicitly using the -d flag
dpetl extract -d path/to/datapackage.yaml
```

```bash
# run extract using the default datapackage descriptor
dpetl extract --descriptor datapackage.yaml

# or explicitly
dpetl extract -d path/to/datapackage.yaml
```

### How it works

The CLI loads the [descriptor](https://datapackage.org/standard/data-package/) (via [`frictionless-py`](https://github.com/frictionlessdata/frictionless-py) package) and iterates over all its [resources](https://datapackage.org/standard/data-resource/). For each resource the extractor reads the custom property `extract_info` and its key `mode` to call the corresponding process (at the moment the `api` and `email` are the available options).

Data package snippet example:

```yaml
# datapackage.yaml
resources:
	- name: invoices
		path: data/invoices.csv
		sources:
			- method: get
				path: https://api.example.com/invoices
    extract_info:
      mode: api

	- name: payroll_from_email
		path: data/payroll.xlsx
    extract_info:
      mode: email
    subject: "Payroll Report"
```

Notes:

- The `api` extractor checks `resource.sources` for an entry with a `method`, and the downloaded file is safe to `resource.path`.
- The `email` extractor uses environment variables to connect to an IMAP server (`EMAIL_USER`, `EMAIL_PWD`, `EMAIL_SMTP`, `EMAIL_BOX`). It searches by `resource.custom['subject']` (defaulting to the resource `name`) and saves the latest matching attachment to `resource.path`.
