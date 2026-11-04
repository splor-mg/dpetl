# Linktable

Builds fact tables and a linktable as a **new data package**, saved to `datapackages/<name>/`. Nothing is published: the generated package is published by [`load`](load.md), like any other package.

```bash
# From a single data package: saved to datapackages/despesa_linktable
dpetl -d datapackages/despesa/datapackage.json linktable

# Across every datapackages/*/datapackage.json with dpetl_linktable
dpetl linktable --name payroll

# Across specific packages
dpetl -d datapackages/despesa/datapackage.json -d datapackages/receita/datapackage.json linktable --name payroll
```

**Remember:** run `dpetl transform` before `dpetl linktable`, and `dpetl load` after it to publish the generated package (see [Order of the commands](how-it-works.md#order-of-the-commands)). The command reads the transformed `datapackage.json` of each package, so field renames (`target`) and anonymization are already applied, and dimensions with the same name in different packages represent the same data. dpetl does not check whether `transform` is up to date, but it stops when a resource has no schema fields.

## Modes

- **Single data package** (exactly one `-d`): the linktable is built from that package. The output package is named `<package>_linktable`, unless `--name` is given, and fact tables are named after the resources (`fact_<resource>`, `key_<resource>`).

- **Across data packages** (no `-d`, or several `-d`): the linktable is built from every package with `dpetl_linktable` (or only the given ones). `--name` is required, and fact tables are prefixed by the package name (`fact_<package>_<resource>`, `key_<package>_<resource>`), keeping resources with the same name in different packages apart.

## Configuration

Each package opts in through the package-level `dpetl_linktable` property:

- `resource_list`: required. Resources used to build the linktable: a resource name, or `{name, facts}` to set the facts of that resource.

- `facts`: required. Fields that are **facts**; every other field is a **dimension**. Each item is a field name or a glob pattern (`*` any characters, `?` one character, `[abc]` one of the characters), matched against the field names of the transformed `datapackage.json` (after `target` renames). A single pattern may be given as a string, and `[]` means the resources have dimensions only. Applies to every resource in `resource_list` that does not set its own `facts`, and is required even when all of them do.

- `enabled`: optional (defaults to `true`). Set it to `false` (or use the shorthand `dpetl_linktable: false`) to leave the package out.

Packages without `dpetl_linktable` are skipped.

```yaml
dpetl_linktable:
  facts: ['vlr_*']               # required
  resource_list:
    - execucao                   # uses the package facts
    - name: empenho              # overrides the package facts
      facts: ['vlr_*', 'qtd_*', total_pago]
    - name: orgao                # dimensions only
      facts: []
```

The `linktable` command takes one option, after the command name:

| Flag | Description |
|------|-------------|
| `--name`, `-n` | Name of the generated data package and of its folder in `datapackages/`. Required across data packages; defaults to `<package>_linktable` with a single `-d`. Only lowercase letters, numbers, `.`, `-` and `_`. |

## How it works

- Each listed resource becomes a fact table `data/fact_<name>.csv.gz`: fields matching `facts` are **facts**, every other field is a **dimension**, and a `key_<name>` column joins the dimension values with `|` (e.g. `2024|A`).

- Across data packages, resources with the same package **and** resource names — typically the same package in different years — are **stacked** into a single fact table. They must have the same dimensions and facts, and the year must be one of the dimensions (e.g. an `ano` field); otherwise rows from different years get the same key.

- The distinct dimension rows of every fact table are combined into `data/linktable.csv.gz`, with one `key_<name>` column per fact table. **Dimensions with the same name in different resources share a single column** — this is what links them together.

- The fact tables, the linktable and a `datapackage.json` are saved to `datapackages/<name>/`.

## Publishing

The generated package has no `dpetl_load` on its first run: add it to `datapackages/<name>/datapackage.json`, then publish with `load`:

```bash
dpetl -d datapackages/orcamento/datapackage.json load
```

Running `linktable` again replaces the resources and the data files (fact tables of resources removed from `resource_list` are deleted), but **keeps the other properties of the existing descriptor**, such as `dpetl_load`, `title` and `description`.

Since the package lives in `datapackages/`, a `dpetl load` without `-d` also publishes it, together with the other packages. It is ignored by `transform` (it has no `datapackage.yaml`) and by `linktable` (it has no `dpetl_linktable`).

## Errors

The command stops with an error, before anything is written, when:

- `--name` is missing across data packages, or is not a valid package name;

- `--name` points to the folder of a source package (a package used to build the linktable, or a folder with a `datapackage.yaml`);

- a package enables `dpetl_linktable` without a `resource_list` or without `facts`;

- a resource in `resource_list` does not exist in the package, or has no schema fields;

- `facts` is not a list of field names or patterns, or a `resource_list` item is neither a name nor `{name, facts}`;

- a field name in `facts` (an item without wildcards) is not a field of the resource. Patterns matching no field are fine, so a package-wide `facts` may list patterns some resources do not use;

- stacked resources (same package and resource names) have different dimensions or facts.

A resource with no facts, or no dimensions, is built with a warning.
