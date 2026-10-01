# Validation

To validate datapackage resources and schemas, dpetl uses `frictionless-py`.

Validation can occur in two stages:

- **Before processing**: validates the entire datapackage when `--validate-before` is used.

- **After processing**: validates each processed resource.

Validation behavior depends on the command:

- `extract`: validates each resource after download. `--validate-before` is not supported.

- `transform`: validates each resource after transformation. Use `--validate-before` to validate the entire datapackage before processing.

- `load`: validates before publishing only if `--validate-before` is used.

## Flags

| Flag | Description |
|------|-------------|
| `--validate-before`, `-vb` | Run validation before processing (not supported for `extract`) |
| `--no-validate`, `-nv` | Skip all validation |
| `--no-stop`, `-ns` | Continue processing resources even when validation errors are found |

See the [API reference](api/helpers.md).
