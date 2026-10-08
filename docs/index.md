# dpetl — Data package ETL

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

Each phase has its own page. See [Extract](extract.md), [Transform](transform.md) and [Load](load.md).

## Design Philosophy

The `dpetl` package follows a [convention over configuration](https://en.wikipedia.org/wiki/Convention_over_configuration) philosophy, treating the Data Package descriptor as the single source of truth for ETL process.

Each resource declares how it should be processed through structured metadata, enabling reproducible, declarative, and version-controlled data workflows.

The goal is to keep the CLI simple while allowing flexible strategies driven entirely by configuration rather than imperative scripting.
