# Documentation

Start with the [repository quick start](../README.md#quick-start), then choose the
guide for the interface or workflow you need.

| Guide | Purpose |
| --- | --- |
| [Architecture](architecture.md) | CSV and database stage ordering, evidence and transaction boundaries |
| [Configuration](configuration.md) | Custom jobs, relative paths, contracts and state locations |
| [Independent engines](engine_boundaries.md) | Module responsibilities and direct Python usage |
| [Data contracts](data_contracts.md) | Logical types, rules, references and schema requirements |
| [Quality gates](data_quality_gates.md) | Record dispositions, gate APIs and stopping policy |
| [Database and CDC](database_cdc.md) | Read-only snapshots, composite cursors and explicit SQLite trigger capture |
| [Reconciliation and recovery](reconciliation.md) | Value checks, replay and failure recovery |
| [Verification](verification.md) | Check commands and recorded local evidence |
| [Migration](migration.md) | Import compatibility, explicit gate names and existing state |
| [Roadmap](roadmap.md) | Implemented scope and planned engineering work |

For changes to the package, see [contributing](../CONTRIBUTING.md).
For input handling, see [security](../SECURITY.md) and
[source provenance](../metadata/README.md).
