# Extract

Runs the ETL extraction phase. Downloads data from external sources (API, email) and saves them locally as configured in the datapackage.

```bash
# Run extract using the default datapackage.yaml descriptor
dpetl extract

# Extract emails received today only
dpetl extract --today-email   # or -t

# Include package name in email subject search pattern
dpetl extract --add-package-name   # or -a

# Add a delay between resource extractions (in seconds)
dpetl extract --delay 5   # or -d 5
```

Each resource in the descriptor must declare an extraction `mode` (`email`, `api` or `cli`) inside its `dpetl_extract` property (see [Example](#example)). If a resource is missing this property, the whole package extraction stops immediately.

## API Extractor

Reads the request settings from the resource's `sources` property:

- `method`: required (e.g. `get`, `post`).

- `path`: required. Treated as a **base URL**, not the full file URL.

    dpetl appends the file name from `resource.path` to it (e.g. `https://api.example.com` + `data/invoices.csv` → `https://api.example.com/invoices.csv`).

- `timeout`: optional, in seconds (defaults to 30).

- `params`, `headers`, `stream`: optional, passed directly to the request.

Once the URL is built, dpetl makes the request and saves the response to `resource.path`.

If the resource declares `extrapaths` (multiple files for the same resource), the same steps run once per path, reusing the same base URL.

## CLI Extractor

Executes local command-line commands to generate or fetch data for the resource.

Configure with `mode: cli` and a list of `arguments` under `dpetl_extract`:

- `arguments`: required. A list of shell commands to run sequentially.

Each command is executed in order. If a command fails, the error is logged and execution continues with the next command.

## Email Extractor

Connects to your IMAP server using environment variables (`EMAIL_USER`, `EMAIL_PWD`, `EMAIL_IMAP`), applying proxy settings (`HTTP_PROXY`/`HTTPS_PROXY`) if set.

It then searches for the **most recent** e-mail matching `criteria`:

- `subject`: if you don't set it in the datapackage (`criteria.subject`), it defaults to the resource name (or `{package_name}_{resource_name}` with `--add-package-name`).

- `date_gte`: if you don't set it in the datapackage (`criteria.date_gte`), it defaults to the most recent e-mail (no date filter). Passing `--today-email` sets it to today's date.

- any other filter supported by [imap-tools](https://pypi.org/project/imap-tools/#user-content--email-attributes) (sender, folder, etc.) can also be set.

Once a matching e-mail is found, its first attachment is saved to `resource.path`. If there is more than one attachment, the extra ones are saved next to it, named `{name}_1{ext}`, `{name}_2{ext}`, and so on.

If the resource declares `extrapaths` (multiple files for the same resource), the same search-and-save logic runs once per path.

## Example

Resources use `dpetl_extract` to declare how each file is downloaded. See the [complete example](example.md).

```yaml
resources:
{% include "extract.yaml" %}
```

See the [API reference](api/extract.md).
