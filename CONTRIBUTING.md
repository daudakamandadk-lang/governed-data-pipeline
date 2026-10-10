# Contributing

Contributions should improve the standalone data-engineering package and retain
its explicit contracts, evidence and recovery behaviour. Keep application-specific
rules and datasets in consuming projects.

## Development setup

Use Python 3.14 to reproduce the CI environment, then create a virtual environment:

```bash
python -m venv .venv
```

Install with the virtual environment's Python. On macOS/Linux:

```bash
.venv/bin/python -m pip install -e . -r requirements-tested.txt
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -e . -r requirements-tested.txt
```

`requirements-tested.txt` records the dependency versions used for verification.
For another supported Python version, install with `-e .` and select compatible
dependencies from the runtime ranges instead. The package supports Python 3.11
or newer; this pinned environment is a separate verification target. See
[verification](docs/verification.md). Reinstall when dependency metadata or entry
points change.

## Proposing a change

- Describe the concrete problem and resulting behaviour. Include a small
  synthetic reproducer where useful.
- Keep changes focused and maintain independent engine responsibilities.
- Preserve existing imports and result semantics, or document an intentional
  migration.
- For stateful work, assess replay, failure timing, reconciliation and when
  progress commits. Test the affected boundaries.
- Update the relevant contract, configuration, API or recovery documentation.

Tests must use temporary synthetic inputs. Do not add source datasets, database
files, credentials or generated evidence to the repository.

## Checks

From the repository root, with the environment's Python:

```bash
python -B -m unittest discover -s tests -p 'test_*.py' -v
python -B scripts/privacy_check.py
git diff --check
```

Start with focused tests while developing, then run the suite before proposing
a code change. Document the actual results and environment; do not reuse an old
verification result for new behaviour. Review staged content after the scan.
See [verification](docs/verification.md) and [security](SECURITY.md).
