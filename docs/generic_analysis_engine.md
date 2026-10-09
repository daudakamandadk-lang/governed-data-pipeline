# Generic Analysis Engine — design and initial WIP

This educational, domain-neutral component begins the analysis layer discussed
for the wider project. It helps an analyst inspect an unfamiliar, approved dataset
without rebuilding basic exploratory analysis each time. It produces mathematical
findings and suggested investigations, not business conclusions. It is an initial
implementation, not a validated production analysis system.

## Architecture and purpose

```text
Governed pipeline: extraction → profiling → validation → cleaning → revalidation
                  → transformation → gates/reconciliation → loading → run evidence
                                              ↓ approved snapshot + evidence
Semantic/context layer → Generic Analysis Engine → Statistical findings
                                                → Next-step analysis router
                                                → Visualization (planned)
                                                → Domain interpretation (external)
                                                → Human judgment / final insight
```

The analysis router is separate from pipeline record routing: it suggests the next
analytical question; it never accepts/quarantines records or advances checkpoints.
Pipeline contracts and gate evidence govern the input. This engine cannot certify
source accuracy or replace upstream validation. A caller selects an accepted,
reconciled snapshot, checks successful run evidence, and calls `analyze` explicitly.
No automatic pipeline callback, database reader, audit writer or gate bypass is
introduced. Failed, quarantined or rejected input should not silently enter analysis.

The wider sequence is **governed pipeline → generic analysis → later credit-risk
statistical engine**. The later engine belongs to the separate domain project and
would interpret approved findings using its own assumptions and reviewed methods.
Credit-risk estimates, scoring, feature engineering and modelling stay outside
this public package. The existing pipeline and compatibility namespace remain intact.

## Semantic/context layer

Pandas dtypes suggest computational roles, not meaning. Numeric columns default
to `measure`, datetimes to `time`, and bool/text/category columns to `category`.
Metadata overrides roles with `identifier`, `measure`, `category`, `time` or
`ignore`. Numeric identifiers and category codes must be declared explicitly;
date strings must be parsed explicitly by the caller. Unique values alone do not
prove identifier status. Mixed object columns are tentative categories.

Caller metadata should describe variable definitions, units, observation grain,
population, time period, source/provenance, domain, caveats and pipeline run/quality
evidence. The WIP retains that context but only validates column names and roles;
it does not enforce a complete semantic contract. Missing context requires human
review. The same correlation in two domains can carry different implications.

## Scope and statistical concepts

| Concept | Initial behavior / outlook |
| --- | --- |
| Counts, mean/median, dispersion, percentiles | Implemented numeric count, missing/non-finite count, mean, standard deviation, variance, min/max, quartiles |
| Categorical frequencies | Implemented counts excluding missing values; may contain sensitive labels |
| Distribution/skew | Implemented constant-column and sample skew checks; undefined skew returns `None` |
| Numeric associations | Implemented pairwise Pearson correlation and usable-pair count; minimum three pairs, constant pairs skipped |
| Group comparisons | Explicit category/measure pairs return count, mean and median; missing group labels excluded and counted |
| Time structure | Datetime count, range, distinct times, order and duplicates; detection hook only |
| Outliers, concentration, rankings, cross-tabs | Discussed; planned, not implemented |
| Trends, growth, period-on-period changes | Discussed; planned after grain/frequency review |
| Significance and effect-size measures | Discussed as conditional future work; no tests or inferential claims implemented |

Missing/non-finite numeric values are excluded from calculations and reported.
Variance and standard deviation use pandas sample conventions (`ddof=1`). Pairwise
correlations can use different subsets; small samples, missingness, repeated
observations and multiple exploratory comparisons limit interpretation. Categories
and measures must be scalar, hashable pandas values; complex numeric measures are
unsupported. The implementation is in-memory and intended for small snapshots;
all numeric pairs and categorical frequencies can become expensive on wide or
high-cardinality input. No transformation, imputation or raw-data mutation occurs.

## Router and visualization

`route` returns transparent `NextStep(action, columns, reason)` values. Its defaults
flag absolute skew ≥ 1 and absolute Pearson correlation ≥ 0.7. These configurable
thresholds are exploratory heuristics, not calibrated significance criteria.
Missing values/non-finite values or absent metadata prompt quality/context review;
two populated groups prompt comparison review; two distinct timestamps prompt
time-structure review. The initial router does not claim large/significant group
differences or automatically prioritize/execute methods.

Later visualization should show distributions, group sizes/comparisons, association
plots and time plots with units, sample counts, missingness and caveats. Charts
help inspect findings; they do not establish causation or replace domain context.
No plotting dependencies, chart output or dashboard are included in this WIP.

## Interpretation and human judgment

The engine may say “strong numeric association: investigate further.” It cannot
say “X causes Y,” explain why a pattern exists, or recommend a domain decision.
The domain layer supplies meaning; a person confirms roles, relevant questions,
assumptions, sampling limitations, confounders and whether follow-up is justified.
Human judgment decides the final insight and how it may be used.

## Minimal usage and package

Install the existing project as described in the root README. No new dependencies.
Run the neutral synthetic example from the repository root:

```powershell
python examples/generic_analysis_demo.py
```

```python
from generic_analysis import analyze

# approved_frame is selected by the caller after pipeline gates/reconciliation.
result = analyze(approved_frame, {
    "grain": "one observation per entity and period",
    "source": "approved synthetic snapshot",
    "columns": {
        "entity_id": {"role": "identifier"},
        "value": {"role": "measure", "unit": "synthetic units"},
        "segment": {"role": "category"},
    },
}, group_pairs=(("segment", "value"),))
```

`models.py` defines `AnalysisResult`; `roles.py` infers roles; `statistics.py`
performs descriptive checks; `engine.py` orchestrates; `router.py` suggests next
steps. Results are Python in-memory values (including pandas group tables), not
a JSON/report format. No raw rows are retained, but aggregates, category labels
and supplied metadata may still disclose sensitive information. Results are not
automatically persisted or published. Apply SECURITY.md before sharing any output;
use synthetic or documented public data only in this repository.

## Roadmap

1. **Now:** review this small WIP, synthetic examples and edge-case tests; confirm
   the role/context contract and keep pipeline integration caller-controlled.
2. **Next:** strengthen semantic metadata and approved-snapshot handoff using
   concrete pipeline evidence; review limitations before expanding scope.
3. **Then:** add discussed outlier/concentration/cross-tab/ranking checks and
   time comparisons incrementally, with explicit assumptions and verification.
4. **Later:** visualizations and reviewed significance/effect-size methods only
   where the analytical question and data support them.
5. **Separate project:** domain interpretation and the later credit-risk
   statistical engine; keep this reusable core domain-neutral.

This roadmap is an outlook, not a claim of implemented capability.
