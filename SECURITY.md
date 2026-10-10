# Security and privacy

The repository contains no bundled datasets. Supply inputs locally through
reviewed configuration. Explicit demonstrations generate small neutral
synthetic fixtures in ignored folders. Keep source permissions and provenance
in the consuming project; see [source provenance](metadata/README.md).

## Reporting a vulnerability

Use the repository's [private vulnerability reporting page](https://github.com/daudakamandadk-lang/governed-data-pipeline/security/advisories/new)
if it is available. Do not include secrets, personal records or operational
data in a public issue. A redacted description or minimal synthetic reproducer
can describe a concern without exposing the source.

## Repository data policy

Never commit operational customer, employee, taxpayer, employer or client data;
credentials or private keys; production connection strings; private network
details; or third-party datasets whose terms do not permit redistribution.

Before sharing a change:

1. Run `python -B scripts/privacy_check.py`.
2. Review staged changes, including generated reports and screenshots.
3. Check that no input records, credentials or restricted source material are included.

The scan checks a configured set of text patterns. A passing scan does not
establish that every secret or identifier has been detected. If a secret has
been committed, revoke or rotate it immediately; deleting the current file
does not remove it from Git history.

## Deployment considerations

Capture installation deliberately modifies a source database. Review the
selected schemas and permissions before installing triggers on your own source.
Run evidence can contain original and cleaned records, so protect local audit
stores using permissions appropriate to the input data. Production security,
access controls, retention and concurrent-writer coordination require design
for the intended environment.
