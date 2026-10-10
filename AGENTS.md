# Repository guidance

## Scope

`governed-data-pipeline` is a standalone Python package for reusable data
engineering. Its supported namespace is `governed_data_pipeline`. Keep the
package independent of notebooks, datasets and consuming applications.

In scope: extraction, profiling, typed validation, cleaning, transformation,
reconciliation, record routing, loading, orchestration, progress and run
evidence. Domain-specific generation, analytics, modelling and application
decisions belong in consumers.

## Architecture and compatibility

- Keep engines independently usable. Orchestration controls stage ordering,
  policy and progress; engines implement focused operations.
- Preserve documented CSV and database transaction boundaries. Advance progress
  only after successful downstream reconciliation and durable evidence.
- Preserve the score-gate compatibility API. Use explicit `evaluate_score_gate`
  and `evaluate_record_gate` names for new callers.
- Require reviewed contracts and explicit source capture installation. Do not
  silently adapt schemas, target constraints, cursors or trigger definitions.
- Describe implemented behaviour accurately and mark future work as planned.
  Do not imply remote CDC, streaming, concurrency or production guarantees.

## Development and verification

Edit source, tests and documentation in this repository. Use an editable
installation for development; exported copies and installed wheels are not
alternate development homes. Follow [CONTRIBUTING.md](CONTRIBUTING.md).

Use focused tests for affected behaviour, including replay and failure boundaries
where state changes. Run the full suite and publication scan before proposing
a package change. Update relevant contracts, configuration or recovery guidance
when externally visible behaviour changes.

## Data policy

Do not bundle datasets, credentials, production connection strings or generated
run evidence. Explicit demonstrations may generate neutral synthetic fixtures
locally in ignored paths. Callers own input provenance and permissions.
Profiling provides observed data-quality evidence; it does not establish source
accuracy or ownership. See [SECURITY.md](SECURITY.md).
