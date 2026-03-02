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
