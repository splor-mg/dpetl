# Transform

Runs the ETL transformation phase. Applies column renaming, format conversion, and other transformations defined in the datapackage (see [Example](#example)).

```bash
# Run transform using the default datapackage.yaml descriptor
dpetl transform

# Generate a secret key for AES‑SIV anonymization
dpetl transform keygen
```

> **Note:** `updated_at` timestamp is added to the package, and the updated descriptor is saved as a JSON file.

## Resource properties

Each resource can be exported using dpetl's built-in pipeline, an external command, or both. When both are used, the command runs after the pipeline, so it can further modify the file dpetl has already written.

After transformation, each resource becomes a single file, with updated `path`, `extrapaths` (removed), `scheme`, `format` and `compression` (if any) values, and inferred `stats`.

> **Tip:** Set `dpetl_transform: false` on a package or resource to skip it.

### Output settings (for the built‑in pipeline)

These are read from the resource's `dpetl_transform` property:

- `path`: optional (defaults to `data`). Folder where the transformed file is saved.

- `format`: optional (defaults to `csv.gz`, a gzip-compressed .csv).

    - Supported formats: `csv`, `txt`, `xlsx` — optionally followed by a compression, like `csv.gz`.

- `encoding`: optional (defaults to `utf-8`). Used for `csv`/`txt` files.

- `delimiter`: optional (defaults to `,`). Field separator used for `csv`/`txt` files.

### `cli`

Runs shell commands as a complement to or replacement for the built‑in pipeline:

- `arguments`: list of commands, executed in order.

- `path`: optional (defaults to `dpetl_transform.path`). Directory where the command's output is expected.

- `pre_process`: optional (defaults to `true`). If `true`, the built‑in pipeline runs first and the command should (over)write that same file. If false, the built‑in pipeline is skipped and the command alone produces the output file.

- `stdin`: optional (defaults to `false`). Pipes the built-in pipeline's output to each command's stdin as .csv instead of writing it to disk.

- `custom`: optional. Defined at the package level, not inside `cli`. Each key is passed to the commands as an environment variable, with its value written as JSON.

The cli's output must be a file named after the resource (case‑insensitive match). Its `format` and new columns are inferred from that file.

## Field properties

Any field in the resource schema may define additional properties to modify its behaviour.

### `target`

If a field defines a `target` property, the field is renamed to the specified target value. After transformation, the `target` property is removed.

### `join`

Adds columns from a .csv file. Useful for attaching labels or descriptions to codes.

- `path`: .csv file to read, relative to the directory where `dpetl` runs.

- `columns`: columns to add, in order, as `{name in the resource: column in the file}`.

- `key`: optional (defaults to the field name). Column of the file matched against the field.

- `by`: optional. Other fields to match, as `{field in the resource: column in the file}`. They must come before the field in the schema.

- `descriptor`: optional. `path` and `resource` of a datapackage to copy the fields of the columns from (defaults to `string` fields).

Unmatched rows get empty values. Identical duplicate rows are dropped; for a key with different values, the first row is kept.

> **Tip:** use `dpetl --verbose` to see details about the join.

### `anonymize`

Fields can be anonymized during transformation by defining an `anonymize` property.

Supported `method` values:

- `sha256`: deterministic hash (first 16 hex chars) – requires no secret key.

- `aes_siv`: deterministic encryption (AES-SIV) – requires `ANONYMIZE_SECRET_KEY`.

    - `context`: optional **context tweak** – uses another field's value as a cryptographic context, so identical values in different contexts produce different tokens.

    - `annotation`: optional **surrogate annotation** – a human‑readable prefix prepended to the encrypted value.

    - `ANONYMIZE_SECRET_KEY`: to generate a secret key for AES‑SIV, use `dpetl transform keygen`.

- `[pattern]`: mask pattern, e.g. `[###-###]` or `[###-###|####-####]`.

    - `#` preserves the original digit.

    - `*` masks the digit (replaces with `*`).

    - Other characters are literals.

You can also add a `filter` condition (a Python expression) to control which rows are anonymized.

## Example

Resources use `dpetl_transform` and the field properties described above. See the [complete example](example.md).

```yaml
resources:
{% include "transform.yaml" %}
```

See the [API reference](api/transform.md).
