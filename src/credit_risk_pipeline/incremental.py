"""Learning prototype: CSV extraction with separately committed JSON progress.

Reads the whole CSV before filtering. Numeric increasing IDs are the first
exercise; strings compare lexically, not as parsed timestamps. State is keyed
by basename: use distinct filenames and one writer per store. Late rows at or
below the watermark, deletes and composite watermarks remain future work.
The connected governed example supplies replay-safe loading separately.
A stale-result check does not coordinate concurrent writers.
"""

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import tempfile

import pandas as pd


@dataclass
class WatermarkState:
    source_name: str
    watermark_column: str
    last_watermark: int | float | str | None


@dataclass
class IncrementalResult:
    data: pd.DataFrame
    previous_watermark: int | float | str | None
    candidate_watermark: int | float | str | None
    row_count: int
    source_path: Path
    watermark_column: str


class JsonWatermarkStore:
    def __init__(self, path="data/staging/watermarks.json"):
        self.path = Path(path)

    def _read_states(self):
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as file:
            states = json.load(file)
        if not isinstance(states, dict):
            raise ValueError("Watermark state must be a JSON object.")
        # Reject a broken store before any source reaches downstream loading.
        for source_name, entry in states.items():
            self._validate_entry(source_name, entry)
        return states

    def _validate_entry(self, source_name, entry):
        # A present but broken entry must never be treated as fresh progress.
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("watermark_column"), str)
            or "last_watermark" not in entry
        ):
            raise ValueError(f"Invalid watermark state for source: {source_name}")
        value = entry["last_watermark"]
        if value is not None and type(value) not in (int, float, str):
            raise ValueError(f"Unsupported stored watermark for source: {source_name}")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"Stored watermark must be finite: {source_name}")

    def load(self, source_name, watermark_column):
        states = self._read_states()
        if source_name not in states:
            return WatermarkState(source_name, watermark_column, None)

        entry = states[source_name]
        if entry["watermark_column"] != watermark_column:
            raise ValueError("Stored watermark column does not match this run.")
        return WatermarkState(source_name, watermark_column, entry["last_watermark"])

    def save(self, state):
        states = self._read_states()
        states[state.source_name] = {
            "watermark_column": state.watermark_column,
            "last_watermark": state.last_watermark,
        }

        # Check serialization before touching the previously saved progress.
        payload = json.dumps(states, indent=4, allow_nan=False)
        self._validate_entry(state.source_name, states[state.source_name])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None

        try:
            # A sibling file keeps replacement on the same filesystem.
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=f".{self.path.name}.", suffix=".tmp", delete=False,
            ) as file:
                temporary_path = Path(file.name)
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())

            # Close the temporary file before replacing the target on Windows.
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


class IncrementalFileExtractionEngine:
    def __init__(self, state_store, read_options=None):
        self.state_store = state_store
        self.read_options = dict(read_options or {})

    def extract(self, path, watermark_column):
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not path.is_file():
            raise ValueError(f"Source is not a file: {path}")

        data = pd.read_csv(path, **self.read_options)
        if watermark_column not in data.columns:
            raise ValueError(f"Watermark column not found: {watermark_column}")
        values = data[watermark_column]
        if values.isna().any():
            raise ValueError(f"Watermark column contains missing values: {watermark_column}")
        if pd.api.types.is_bool_dtype(values):
            raise ValueError(f"Boolean watermark values are unsupported: {watermark_column}")
        if values.isin([math.inf, -math.inf]).any():
            raise ValueError(f"Watermark column must contain finite values: {watermark_column}")

        state = self.state_store.load(path.name, watermark_column)
        previous_watermark = state.last_watermark
        if previous_watermark is None:
            incremental_data = data.copy()
        else:
            incremental_data = data[values > previous_watermark].copy()

        if incremental_data.empty:
            candidate_watermark = previous_watermark
        else:
            candidate_watermark = incremental_data[watermark_column].max()

        # pandas numeric maxima may be NumPy scalars; JSON needs Python scalars.
        if candidate_watermark is not None and hasattr(candidate_watermark, "item"):
            candidate_watermark = candidate_watermark.item()

        return IncrementalResult(
            data=incremental_data,
            previous_watermark=previous_watermark,
            candidate_watermark=candidate_watermark,
            row_count=len(incremental_data),
            source_path=path.resolve(),
            watermark_column=watermark_column,
        )

    def commit(self, path, watermark_column, result):
        path = Path(path)
        if path.resolve() != result.source_path or watermark_column != result.watermark_column:
            raise ValueError("Result source or watermark column does not match this commit.")
        current = self.state_store.load(path.name, watermark_column)
        if current.last_watermark != result.previous_watermark:
            raise ValueError("Watermark changed since extraction; extract again before committing.")

        self.state_store.save(WatermarkState(
            source_name=path.name,
            watermark_column=watermark_column,
            last_watermark=result.candidate_watermark,
        ))
