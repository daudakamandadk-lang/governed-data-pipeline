# AGENTS.md

## Project identity

This repository is the public, standalone data-engineering portfolio project.

Repository name:
`governed-data-pipeline`

The project is a reusable governed data pipeline and should not be framed as a credit-risk-specific pipeline.

## Architecture direction

The target pipeline is:

```text
Sources
  -> Extraction
     - full-file
     - chunked
     - incremental
     - database
     - API
     - CDC
  -> Profiling
  -> Validation
  -> Cleaning
  -> Revalidation
  -> Transformation
  -> Reconciliation
  -> Classification / Routing
     - accepted
     - corrected
     - quarantined
     - rejected
  -> Loading
  -> Audit / Run Evidence
```

## Portfolio intent

The public repository should present a professional, integrated data-engineering story. Keep components modular, but connect them through orchestration so the repository demonstrates an end-to-end governed pipeline rather than unrelated scripts.

Do not add credit-risk modelling, feature engineering, scoring, or ML-specific logic here. Those belong to the separate private project.

## Current development priorities

1. Preserve the existing profiler, cleaning and loading work.
2. Add and integrate extraction patterns.
3. Complete validation, cleaning, transformation, reconciliation and routing boundaries.
4. Add run state, run IDs, audit evidence and exception handling.
5. Add an end-to-end orchestrated example.
6. Add tests and clear architecture documentation.
7. Add production tooling such as Docker/orchestration/CI only after the Python pipeline is stable.

## Working style

- Develop this package's generic engines, tests and documentation in this
  checkout. Ignored staging/export copies in consuming projects are historical
  snapshots, not development homes.
- Private learning modules may have different contracts. Assess shared fixes in
  each affected project and verify its behaviour rather than syncing source trees.
- Keep the retained score-gate API compatible. Use explicit
  `evaluate_score_gate` and `evaluate_record_gate` names for new callers.

- Prefer small, understandable modules over a single large pipeline file.
- Keep orchestration thin; business logic belongs in engines/components.
- Do not claim a capability in README/docs until it is actually implemented or clearly marked planned.
- Preserve a professional public surface: no bundled datasets or domain source catalogue. Neutral synthetic fixtures are generated locally only on explicit demonstration runs and stay ignored.

## Repository boundaries

Only `src/governed_data_pipeline/` is a supported package. Domain-specific source
datasets, defaults, generation, statistical exploration and analytics windows
belong to separate consuming projects. The statistical exploration lab is a
separate component and must not be placed inside extraction or profiling engines.
Profiling here provides descriptive data-quality evidence for pipeline runs.
A pristine checkout contains no data directory. Keep caller-owned inputs,
generated demonstrations and their run evidence local and excluded from Git.
