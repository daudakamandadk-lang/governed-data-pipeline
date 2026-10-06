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

- Prefer small, understandable modules over a single large pipeline file.
- Keep orchestration thin; business logic belongs in engines/components.
- Do not claim a capability in README/docs until it is actually implemented or clearly marked planned.
- Preserve a professional public surface: sample/synthetic data only, no private or restricted data.
