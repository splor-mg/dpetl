# How it works

The CLI loads Data Package descriptor(s) (via the `frictionless-py` Python package) and iterates over its resources.

By default, the CLI looks for:

- `datapackage.yaml` when running `extract` or `transform`

- `datapackage.json` when running `load` or `linktable`

If you have **multiple data packages**, place them in a `datapackages/` folder (each in its own subdirectory) and dpetl will process all of them.

You can also **specify one or more descriptors** manually using the `-d` or `--descriptor` flag (it can be passed multiple times). This is useful when you want to test a specific configuration or process a file that is not in the default location.

`-d` is a global flag, so it goes **before** the command name:

```bash
# Single descriptor
dpetl -d configs/datapackage_payroll.yaml transform

# Multiple descriptors
dpetl -d datapackages/sales/datapackage.yaml -d datapackages/hr/datapackage.yaml extract
```

## Order of the commands

Each command reads what the previous one wrote, so they run in this order:

```bash
dpetl extract                      # downloads the source files
dpetl transform                    # reads datapackage.yaml, writes the files and datapackage.json
dpetl linktable --name payroll   # optional. Reads datapackage.json, writes datapackages/payroll/
dpetl load                         # reads datapackage.json and publishes each package
```

- `transform` writes the `datapackage.json` that `load` and `linktable` read. Run it again whenever the `datapackage.yaml` or the source data change.

- `linktable` does not publish anything: it saves a new data package in `datapackages/<name>/`. Run it **before** `load`, so that `load` (without `-d`) publishes the linktable package together with the other packages. Set its `dpetl_load` first (see [Linktable](linktable.md#publishing)).

## Skipping a command

You can **skip a command entirely for a given package** by setting `enabled: false` under the corresponding `dpetl_extract`, `dpetl_transform`, `dpetl_load` or `dpetl_linktable` key at the package level in the descriptor.

```yaml
# full form
dpetl_extract:
  enabled: false

# shorthand, equivalent to the above
dpetl_extract: false
```

## Environment file

Environment variables for email extraction, GitHub authentication, and proxy settings can be defined in a `.env` file in the current working directory — it is loaded automatically.

See the [Options](options.md#environment-variables) page for the complete list of supported variables and their usage.

A complete descriptor is shown in the [Example datapackage](example.md) page.
