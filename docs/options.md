# Options

## Global flags

Flags that can be used with any command:

| Flag | Description |
|------|-------------|
| `--descriptor`, `-d` | Path to one or more datapackage descriptors (repeatable) |
| `--no-validate`, `-nv` | Skip datapackage validation |
| `--no-stop`, `-ns` | Continue even if validation fails (do not exit with error) |
| `--validate-before`, `-vb` | Run validation before processing (not supported for `extract`) |
| `--verbose` | Enable debug logging (also writes logs to `dpetl.debug.log`) |
| `--quiet`, `-q` | Suppress all logs except warnings and errors |
| `--version`, `-v` | Show version number and exit |
| `--help` | Show help message |


## Environment variables

All variables above can also be set in a `.env` file in the current directory instead of the shell environment.

| Variable | Used By | Description |
|----------|---------|-------------|
| `EMAIL_USER` | extract (email mode) | Username for IMAP email connection |
| `EMAIL_PWD` | extract (email mode) | Password for IMAP email connection |
| `EMAIL_IMAP` | extract (email mode) | IMAP server address (e.g., imap.gmail.com) |
| `HTTP_PROXY` | extract (email mode) | Proxy settings for IMAP connections* |
| `ANONYMIZE_SECRET_KEY` | transform | Secret key for AES‑SIV anonymization |
| `GH_TOKEN` | load | GitHub Personal Access Token |
| `GH_APP_ID` | load | GitHub App ID |
| `GH_APP_PRIVATE_KEY` | load | GitHub App private key |
| `GH_APP_INSTALLATION_ID` | load | GitHub App installation ID (optional) |

**\* Proxy notes:** If your network requires a proxy, dpetl supports both uppercase and lowercase proxy environment variables. Use the format `http://user:pwd@host:port` when authentication is required.
