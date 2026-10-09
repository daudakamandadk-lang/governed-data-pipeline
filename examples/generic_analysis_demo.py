"""WIP example using only small, neutral synthetic observations; no output files."""

import pandas as pd

from generic_analysis import analyze


def main():
    data = pd.DataFrame({
        "entity_id": range(1, 7),
        "period": pd.date_range("2026-01-01", periods=6),
        "segment": ["A", "A", "A", "B", "B", "B"],
        "value": [1., 2., 3., 4., 5., 20.],
        "other_value": [2., 4., 6., 8., 10., 40.],
    })
    result = analyze(data, {
        "grain": "one synthetic observation per entity",
        "source": "synthetic example",
        "columns": {"entity_id": {"role": "identifier"}},
    }, group_pairs=(("segment", "value"),))
    for step in result.next_steps:
        print(step.action, step.columns, step.reason)


if __name__ == "__main__":
    main()
