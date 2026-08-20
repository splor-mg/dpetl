## 0.12.0 (2026-08-20)

### Feat

- **cli**: add transform keygen subcommand
- **transform**: add anonymization module and field properties

## 0.11.0 (2026-08-13)

### Feat

- **actions**: add automated coverage badge and package release workflow
- **load**: add GitHub App authentication support
- **transform**: add custom delimiter support for CSV/TXT exports
- **extract**: add CLI extractor mode to run shell commands
- **logging**: add verbose and quiet flags, improve log messages across modules

### Fix

- sync local version with PyPI 0.10.0
- **ci**: install github-app extra in coverage_release workflow
- **ci**: install github-app extra in test workflow
- **actions**: publish coverage badge only on main
- **actions**: configure git user for coverage badge commit

## 0.10.0 (2026-07-21)

### Feat

- **extract**: add extraction module with validation
- **transform**: always export descriptor as JSON and add datapackage validation
- **load**: skip empty commits and add datapackage validation
- **transform**: add datapackage validation

### Fix

- **load**: fix f-string syntax error on line 43
- **email**: avoid setting date_gte to None when not filtering by today
- **api**: handle uppercase HTTP method in sources

### Refactor

- **validate**: move validation logic to helpers for reuse across phases
- **iterator**: remove toml support and simplify descriptor discovery
- **cli**: migrate from argparse to typer

## 0.9.0 (2026-06-29)

### Feat

- **actions**: add test and test_coverage actions
- **README.md**: add coverage badge to README
- **load**: add initial structure
- **load**: add load operation
- **load**: add load subcommands to CLI
- **transform**: add transform subcommands to CLI
- **transform**: add initial structure
- **transform**: add transform operation
- **extract**: add operation argument

### Refactor

- **pyproject**: review rre and post test tasks
- **load**: use descriptor parameters for repository configuration
- **load**: improve GitHub integration and repository configuration
- **load**: remove CLI arguments
- **transform**: reorganize transform code
- **transform**: use dpetl_transform for configurable output

## 0.8.2 (2026-04-23)

### Fix

- **extract**: improve attachment name

## 0.8.1 (2026-04-08)

### Fix

- **extract**: exit 1 when email vars aren't passed

## 0.8.0 (2026-03-26)

### Feat

- **extract**: add multpart file in extract api
- **extract**: download and save files in chunck

### Fix

- **extract**: check if resource.path exists

## 0.7.0 (2026-03-12)

### Feat

- **extract**: add recursive extraction

### Refactor

- **.env**: remove .env.example

## 0.6.0 (2026-03-05)

### Feat

- **extract**: add --add-package-name to extract command

### Refactor

- **format**: run task format

## 0.5.1 (2026-03-02)

### Fix

- **pyproject**: downgrade python version required

## 0.5.0 (2026-03-02)

### Feat

- **helpers**: add network helper
- **extract**: add --today-email flag
- **extract**: add multipart file extract func

### Refactor

- **.env**: change smtp env varts to imap

## 0.4.2 (2026-02-26)

### Fix

- **fix-sintaxe-error**: remove ( from long text

### Refactor

- **extract**: improve code formating

## 0.4.1 (2026-02-26)

### Fix

- **extract**: fix dptel typo

## 0.4.0 (2026-02-26)

### Feat

- **extract**: improves dpetl extract email

## 0.3.1 (2026-02-24)

### Refactor

- **task**: add push origin main and tags into task publish

## 0.3.0 (2026-02-24)

### BREAKING CHANGE

- See https://github.com/splor-mg/etl-cli/issues/6#issuecomment-3953910191

### Feat

- **dpetl**: change package name to dpetl

### Refactor

- **task**: add task bump

## 0.2.0 (2026-02-24)

### BREAKING CHANGE

- See #2
- Fix #1

### Feat

- **etl**: add extract api command
- **extract**: start review extract api function
- **extract**: add extract email command
- **extract**: add extract email command
- **extract**: add extract emails function
- **extract**: add initial structure
- **actions**: add failed notification actions
- **poetry**: install python-dotenv
- **.env**: add .env.example file
- **actions**: add sync actions
- **taskipy**: add task list
- **poetry**: add poetry and some libs
- **actions**: add actions to sync templates
- **pyproject.toml**: add linters and formaters
- **taskipy**: add task list
- **poetry**: add poetry and some libs
- **.editorconfig**: split .py and .md configuration
- **actions**: add .github/workflows folder

### Fix

- **actions**: fix create pr step not starting

### Refactor

- **pyproject.toml**: update repo template upstream
- **etl_cli**: review etl_cli config
- **actions**: improve get upstream url
- **actions**: add step to the action job_id
- **my_pkg**: add my_pkg and tests
