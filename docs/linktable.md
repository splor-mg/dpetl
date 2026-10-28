# Linktable

Builds a linktable **across data packages** and loads it into a new GitHub repository named `linktable`, or into the Postgres schema `linktable` when the packages use `target: postgres`.

```bash
# Run linktable over ./datapackage.json or every datapackages/*/datapackage.json
dpetl linktable

# Run linktable over specific packages
dpetl -d datapackages/despesa/datapackage.json -d datapackages/receita/datapackage.json linktable
```

**Remember:** run `dpetl transform` before `dpetl linktable`. The command reads the transformed `datapackage.json` of each package, so field renames (`target`) and anonymization are already applied, and dimensions with the same name in different packages represent the same data. dpetl does not check whether `transform` was run or whether its output is up to date.

To build a linktable **within a single data package**, use the [`package_linktable`](transform.md#package-linktable) option on `dpetl_transform` instead.

## Configuration

Each package opts in through the package-level `dpetl_linktable` property:

- `resource_list`: required. Names of the resources used to build the linktable.

- `enabled`: optional (defaults to `true`). Set it to `false` (or use the shorthand `dpetl_linktable: false`) to leave the package out.

Packages without `dpetl_linktable` are skipped.

```yaml
dpetl_linktable:
  resource_list: [execucao, empenho]
```

## How it works

- Each listed resource becomes a fact table `data/fact_<package>_<resource>.csv.gz`: fields starting with `vlr_` are **facts**, every other field is a **dimension**, and a `key_<package>_<resource>` column joins the dimension values with `|` (e.g. `2024|A`). The package prefix keeps resources with the same name in different packages apart.

- Resources with the same package **and** resource names — typically the same package in different years — are **stacked** into a single fact table. They must have the same dimensions and facts, and the year must be one of the dimensions (e.g. an `ano` field); otherwise rows from different years get the same key.

- The distinct dimension rows of every fact table are combined into `data/linktable.csv.gz`, with one `key_<package>_<resource>` column per fact table. **Dimensions with the same name in different packages share a single column** — this is what links the packages together.

- The fact tables, the linktable and a `datapackage.json` are published in a single commit, following the same steps as [`load`](load.md).

The destination reuses the `owner`, `level`, `visibility`, `target` and `lfs` from the packages' `dpetl_load` property, so these values must be the same in every package. With an LFS `url`, use the `{repo}` placeholder so it also points to the `linktable` repository.

## Errors

The command stops with an error, before anything is published, when:

- a package enables `dpetl_linktable` without a `resource_list`;

- a resource in `resource_list` does not exist in the package;

- stacked resources (same package and resource names) have different dimensions or facts;

- the packages' `dpetl_load` settings point to different `owner`, `level`, `visibility`, `target` or `lfs`.
