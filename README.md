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

- `datapackage.json` when running `load`

Then it runs each phase on its resources, following the `dpetl_extract`, `dpetl_transform` and `dpetl_load` properties declared in it.

If you have more than one data package, place each one in its own subdirectory of `datapackages/`.


## Documentation

Full documentation, with a page for each phase, the descriptor details and the API reference, at <https://splor-mg.github.io/dpetl/>.
