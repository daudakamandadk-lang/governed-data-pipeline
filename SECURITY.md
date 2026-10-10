# Security and Privacy

This is a public portfolio repository. Confidentiality takes precedence over convenience.

## Never commit

- employer or client datasets;
- taxpayer/customer/employee operational data;
- passwords, API keys, access tokens or private keys;
- production database connection strings;
- private hostnames, IP addresses, VPN details or internal network documentation;
- restricted third-party datasets that do not permit redistribution.

## Intended data

The public checkout contains no bundled datasets. Supply caller-owned inputs locally through reviewed configuration. Explicit demonstration runs generate small neutral synthetic fixtures in ignored local folders. Record source provenance and permissions in the consuming project; see [source provenance](metadata/README.md).

## Before publishing

1. Run `python scripts/privacy_check.py`.
2. Review staged changes.
3. Confirm no raw operational data or secrets are included.
4. Inspect notebooks, screenshots and generated reports for hidden identifiers.
5. If a real secret is ever committed, rotate/revoke it immediately; deleting only the current file does not remove it from Git history.
