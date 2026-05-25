# Testing and Coverage Plan

This document plans the first testing and documentation improvements for
`dpetl`. The goal is to move step by step, starting with low-risk CLI parser
tests before testing extract, transform, load, network, e-mail, or GitHub
behavior.

## Current Findings

- `tests/test_main.py` is still a template-style test. It imports
  `dpetl.cli` and expects `cli.hello()`, but `hello()` does not exist.
- `poetry run pytest -s -x -vv` currently fails because of that missing
  `hello()` function.
- `poetry run task test` currently runs `pre_test` first, and `pre_test`
  runs `task lint`. Because lint currently reports many issues, `task test`
  fails before pytest starts.
- `post_test = coverage html` currently does not work by itself because the
  test command does not generate coverage data. It reports: `No data to
  report.`
- The README examples put `--descriptor/-d` after the `extract` command, but
  the CLI defines `--descriptor/-d` on the root parser. The CLI behavior is the
  intended behavior, so the README should be fixed.

## Step 1: Add Initial CLI Parser Tests

Replace the existing `tests/test_main.py` with CLI parser tests, or create a
new `tests/test_cli.py` and remove the old template test.

Suggested tests:

```python
import pytest

from dpetl import cli


def test_extract_uses_default_descriptor():
    args = cli.build_parser().parse_args(['extract'])

    assert args.command == 'extract'
    assert args.descriptor == 'datapackage.yaml'
    assert args.today_email is False
    assert args.add_package_name is False


def test_descriptor_long_flag_is_parsed_before_command():
    args = cli.build_parser().parse_args(
        ['--descriptor', 'custom.yaml', 'extract']
    )

    assert args.command == 'extract'
    assert args.descriptor == 'custom.yaml'


def test_descriptor_short_flag_is_parsed_before_command():
    args = cli.build_parser().parse_args(['-d', 'custom.yaml', 'extract'])

    assert args.command == 'extract'
    assert args.descriptor == 'custom.yaml'


def test_descriptor_after_command_is_invalid():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            ['extract', '--descriptor', 'custom.yaml']
        )


def test_extract_email_flags_are_parsed():
    args = cli.build_parser().parse_args(
        ['extract', '--today-email', '--add-package-name']
    )

    assert args.today_email is True
    assert args.add_package_name is True


def test_command_is_required():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])
```

Why start here:

- These tests do not touch real descriptors.
- They do not connect to e-mail, APIs, or GitHub.
- They document the intended CLI contract.
- They reveal README examples that are inconsistent with the actual parser.

## Step 2: Add Command Handler Tests

After parser tests pass, test each command module with `monkeypatch` so no real
ETL operation runs.

For example, for `extract`:

```python
from argparse import Namespace

from dpetl.extract import cli as extract_cli


def test_extract_handle_command_calls_descriptor_iteration(monkeypatch):
    calls = []

    def fake_descriptor_iteration(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        extract_cli,
        'descriptor_iteration',
        fake_descriptor_iteration,
    )

    args = Namespace(
        command='extract',
        descriptor='custom.yaml',
        today_email=True,
        add_package_name=False,
        func=extract_cli.handle_command,
    )

    extract_cli.handle_command(args)

    assert calls == [
        {
            'operation': 'extract',
            'command': 'extract',
            'descriptor': 'custom.yaml',
            'today_email': True,
            'add_package_name': False,
            'func': extract_cli.handle_command,
        }
    ]
```

This same pattern can later be repeated for `transform` and `load`.

## Step 3: Improve README Usage Examples

The README should show the descriptor flag before the command:

```bash
# Run extract using the default datapackage.yaml descriptor
dpetl extract

# Specify a descriptor explicitly
dpetl --descriptor path/to/datapackage.yaml extract
# or
dpetl -d path/to/datapackage.yaml extract
```

The explanation should mention that `--descriptor/-d` is a global option shared
by all ETL commands.

Suggested wording:

```markdown
The `--descriptor/-d` option is global, so it must be passed before the ETL
command. This keeps descriptor selection consistent across `extract`,
`transform`, and `load`.
```

## Step 4: Review the Test Task

Current task:

```toml
test = { cmd = 'pytest -s -x -vv', help = 'Runs unit tests.' }
```

This is useful while debugging because:

- `-s` shows print/log output immediately.
- `-x` stops after the first failure.
- `-vv` gives verbose test names.

But it is not ideal as the default project test command because:

- `-s` can make normal test output noisy.
- `-x` hides later failures.
- It does not collect coverage.

Suggested split:

```toml
test = { cmd = 'pytest -vv --cov=dpetl --cov-report=term-missing --cov-report=xml', help = 'Runs unit tests with coverage.' }
test_debug = { cmd = 'pytest -s -x -vv', help = 'Runs unit tests in debug mode.' }
```

## Step 5: Review Pre and Post Tasks

Current tasks:

```toml
pre_test = { cmd = 'task lint', help = 'Runs linters before running the tests.' }
post_test = { cmd = 'coverage html', help = 'Generates a coverage report after the tests.' }
```

The current `pre_test` means `task test` cannot run tests until all lint issues
are fixed. That can be good for CI, but it slows down early test writing.

Suggested approach:

```toml
test = { cmd = 'pytest -vv --cov=dpetl --cov-report=term-missing --cov-report=xml', help = 'Runs unit tests with coverage.' }
test_debug = { cmd = 'pytest -s -x -vv', help = 'Runs unit tests in debug mode.' }
coverage_html = { cmd = 'coverage html', help = 'Generates an HTML coverage report.' }
check = { cmd = 'task lint && task test', help = 'Runs lint and tests.' }
```

Then remove or reconsider `pre_test` and `post_test`.

Why:

- `task test` should answer one question: do tests pass?
- `task check` can answer the stricter CI-style question: does lint plus tests
  pass?
- `coverage_html` should be explicit because HTML coverage is useful locally,
  but it is not always needed on every test run.

If keeping `post_test`, make sure the test command uses `--cov=dpetl`, otherwise
`coverage html` has no data.

## Step 6: Add Coverage Badge to README

Use a generated SVG badge committed to the repository. This keeps the project
independent from external coverage services and makes the README badge work
directly from the files in the repository.

Important tradeoff:

- The badge only changes when someone regenerates it and commits the updated
  SVG file.
- This is simple and transparent, but it can become stale if the badge is not
  updated after test coverage changes.

Suggested workflow:

- Add a dev dependency such as `coverage-badge`.
- Run tests with coverage:

```bash
pytest --cov=dpetl --cov-report=term-missing --cov-report=xml
```

- Generate a local badge file, for example `coverage.svg`:

```bash
coverage-badge -o coverage.svg -f
```

- Add this to the README:

```markdown
![Coverage](coverage.svg)
```

Suggested task:

```toml
coverage_badge = { cmd = 'coverage-badge -o coverage.svg -f', help = 'Generates the README coverage badge.' }
```

After running `task test`, run `task coverage_badge` and commit the updated
`coverage.svg` together with the code or test changes that changed coverage.

`coverage_html` is independent from this badge workflow. It generates a
browsable local report in `htmlcov/`, but it is not required for
`coverage_badge` to work. The badge only needs the coverage data generated by
`task test`.

Normal badge update flow:

```bash
poetry run task test
poetry run task coverage_badge
```

## Suggested Order of Work

1. Replace the template test with `tests/test_cli.py`.
2. Run `poetry run pytest -vv`.
3. Fix README CLI usage examples.
4. Change the test task to include coverage.
5. Decide whether `pre_test` and `post_test` should stay automatic or become
   explicit tasks.
6. Add `coverage-badge` as a dev dependency.
7. Add a `coverage_badge` task.
8. Generate and commit `coverage.svg`.
9. Add the local coverage badge to README.

## First Definition of Done

The first small milestone is complete when:

- CLI parser tests pass.
- The README shows `--descriptor/-d` before the command.
- `task test` runs pytest successfully.
- Coverage is collected during tests.
- The project has a clear path for a README coverage badge.
