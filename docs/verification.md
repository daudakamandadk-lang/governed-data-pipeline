# Verification

Run checks from the repository root using the Python environment in which the
package is installed:

```bash
python -B -m unittest discover -s tests -p 'test_*.py' -v
python -B scripts/privacy_check.py
git diff --check
```

The suite uses temporary synthetic files and databases. It exercises engine
contracts and connected workflows, including identical replay, conflicting
values, source/capture drift, invalid related state and failure timing around
audit, load and progress commits. Gate-interface checks preserve the explicit
and compatibility imports.

The publication scan checks configured secret/privacy text patterns. Review
the proposed changes as well; a passing scan is not comprehensive data or
security verification.

## Continuous integration

The [CI workflow](../.github/workflows/ci.yml) installs the package with
`requirements-tested.txt` on Python 3.14, checks dependency consistency, runs the
tests and publication scan, and builds a wheel. See [GitHub Actions](https://github.com/daudakamandadk-lang/governed-data-pipeline/actions/workflows/ci.yml)
for the status and logs of a particular commit. Configured checks and a completed
hosted run are separate evidence.

## Recorded local result

| Date | Environment | Result |
| --- | --- | --- |
| 2026-10-10 | Python 3.14.6; pandas 3.0.6; NumPy 2.5.3 | 120 tests passed; publication scan passed |

This result was obtained locally. It does not establish that every supported
Python/dependency combination has been tested. Runtime dependencies specify
ranges; `requirements-tested.txt` records the versions used for verification.
Rerun checks for your checkout and environment after changing engines,
contracts or configuration.

The CSV and SQLite demonstrations are also available as manual end-to-end
checks; see the [README](../README.md#demonstrations). Keep their generated
inputs, databases and progress excluded from Git.
