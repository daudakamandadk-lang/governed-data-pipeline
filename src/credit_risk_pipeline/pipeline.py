"""Connected learning orchestration through quality gates, durable load and commit.

One append-only CSV job, one writer, increasing integer watermarks. No database
extraction, CDC, credit-risk decisions or ML are implemented by this module.
"""

from dataclasses import asdict, dataclass, field
import json
import logging
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

import pandas as pd

from .cleaning import CleaningEngine
from .loading import IdempotentSqliteLoader
from .values import digest, file_digest
from .incremental import IncrementalFileExtractionEngine, JsonWatermarkStore
from .transformation import BandRule, BandTransformer, _validate_identifier
from .record_gates import GateThresholds, classify_records, evaluate_gate
from .profiling import profile_data
from .audit import RunJournal
from .validation import validate_fields, validate_schema


logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    job_name: str
    source: Path
    database_path: Path
    watermark_path: Path
    target_table: str
    watermark_column: str
    schema: dict
    date_formats: dict = field(default_factory=dict)
    gate: GateThresholds = field(default_factory=GateThresholds)
    sum_columns: list = field(default_factory=list)
    transform: dict | None = None
    reference_paths: dict = field(default_factory=dict)
    max_attempts: int = 2

    @classmethod
    def from_json(cls, path, workspace=None):
        settings = json.loads(Path(path).read_text(encoding="utf-8"))
        root = Path(workspace or Path.cwd()).resolve()
        for name in ("source", "database_path", "watermark_path"):
            settings[name] = (root / settings[name]).resolve()
        settings["reference_paths"] = {
            table: (root / value).resolve() for table, value in settings.get("reference_paths", {}).items()
        }
        settings["gate"] = GateThresholds(**settings.get("gate", {}))
        return cls(**settings)

    def policy(self):
        result = asdict(self)
        for name in ("source", "database_path", "watermark_path"):
            result[name] = str(Path(result[name]).resolve())
        result["reference_paths"] = {key: str(Path(value).resolve()) for key, value in self.reference_paths.items()}
        result["pipeline_version"] = "governed-csv-sqlite-v2"
        return result


@dataclass
class PipelineRun:
    run_id: str
    status: str
    extracted: int = 0
    accepted: int = 0
    quarantined: int = 0
    rejected: int = 0
    inserted: int = 0
    reused: int = 0
    corrected_cells: int = 0
    gate_outcome: str | None = None
    previous_watermark: object = None
    candidate_watermark: object = None


class GovernedPipeline:
    def __init__(self, config, *, journal=None, loader=None, extractor=None):
        self.config = config
        validate_schema(config.schema)
        paths = [Path(value).resolve() for value in (config.source, config.database_path, config.watermark_path)]
        if len(set(paths)) != 3:
            raise ValueError("Source, target database and progress paths must be distinct")
        if not config.job_name:
            raise ValueError("A job name is required")
        if type(config.max_attempts) is not int or not 1 <= config.max_attempts <= 5:
            raise ValueError("max_attempts must be an integer between 1 and 5")
        if config.schema["columns"].get(config.watermark_column, {}).get("dtype") != "integer":
            raise ValueError("This incremental learning job requires an integer watermark field")
        if not config.schema["columns"][config.watermark_column].get("required"):
            raise ValueError("The watermark field must be required")
        if config.watermark_column != config.schema["primary_key"] and not config.schema["columns"][config.watermark_column].get("unique"):
            raise ValueError("The increasing watermark field must also be unique")
        evaluate_gate([], config.gate)  # Reject invalid thresholds before any job writes.
        _validate_identifier(config.target_table, "table")
        if config.target_table.startswith("etl_"):
            raise ValueError("Target names cannot use the audit table prefix etl_")
        for column in config.sum_columns:
            if config.schema["columns"].get(column, {}).get("dtype") not in {"integer", "float"}:
                raise ValueError(f"Reconciliation total requires a numeric field: {column}")
        if config.transform:
            settings = config.transform
            _validate_identifier(settings["derived_column"], "column")
            if settings["derived_column"] in config.schema["columns"]:
                raise ValueError("Transformation cannot overwrite a schema field")
            if config.schema["columns"].get(settings["source_column"], {}).get("dtype") not in {"integer", "float"}:
                raise ValueError("Band source must be a numeric schema field")
            BandTransformer(settings["source_column"], settings["derived_column"],
                            [BandRule(**item) for item in settings["rules"]])
        self.journal = journal or RunJournal(config.database_path)
        self.loader = loader or IdempotentSqliteLoader(config.database_path)
        text_types = {"string", "category", "date", "timestamp", "boolean"}
        dtype = {name: str for name, rules in config.schema["columns"].items() if rules["dtype"] in text_types}
        dtype[config.watermark_column] = "Int64"
        self.extractor = extractor or IncrementalFileExtractionEngine(
            JsonWatermarkStore(config.watermark_path),
            read_options={"dtype": dtype, "keep_default_na": False},
        )

    def _stage(self, run_id, name, function, attempt):
        started = time.monotonic()
        self.journal.event(run_id, name, "started", {"attempt": attempt})
        logger.info("run=%s stage=%s started", run_id, name)
        try:
            result = function()
        except Exception as error:
            self.journal.event(run_id, name, "failed", {"attempt": attempt, "error": str(error)})
            raise
        self.journal.event(run_id, name, "succeeded", {
            "attempt": attempt, "elapsed_ms": round((time.monotonic() - started) * 1000, 3)
        })
        return result

    def _attempt(self, run_id, attempt):
        config = self.config
        stage = lambda name, function: self._stage(run_id, name, function, attempt)
        source_hash = stage("source_fingerprint", lambda: file_digest(config.source))
        extracted = stage("extract", lambda: self.extractor.extract(config.source, config.watermark_column))
        summary = PipelineRun(run_id, "running", extracted=extracted.row_count,
                              previous_watermark=extracted.previous_watermark,
                              candidate_watermark=extracted.candidate_watermark)
        def read_references():
            tables = {}
            hashes = {}
            for table, path in config.reference_paths.items():
                hashes[table] = file_digest(path)
                dtype = {}
                for rules in config.schema["columns"].values():
                    target = rules.get("foreign_key", "")
                    if target.startswith(table + ".") and rules["dtype"] in {"string", "category"}:
                        dtype[target.split(".", 1)[1]] = str
                tables[table] = pd.read_csv(path, dtype=dtype, keep_default_na=False)
            return tables, hashes
        references, reference_hashes = stage("references", read_references)
        self.journal.event(run_id, "lineage", "fingerprints", {
            "source": source_hash, "references": reference_hashes,
        })
        profile = stage("profile", lambda: profile_data(extracted.data))
        self.journal.event(run_id, "profile", "summary", {"rows": profile["rows"]})
        before = stage("validate_before", lambda: validate_fields(extracted.data, config.schema, references))
        cleaned = stage("clean", lambda: CleaningEngine().clean(
            extracted.data, config.schema, config.date_formats
        ))
        after = stage("validate_after", lambda: validate_fields(cleaned.data, config.schema, references))
        dispositions = stage("classify", lambda: classify_records(
            cleaned.data, config.schema, cleaned.corrections, [*cleaned.issues, *after.issues]
        ))
        gate = stage("gate", lambda: evaluate_gate(dispositions, config.gate, batch_failures=after.batch_failures))
        self.journal.event(run_id, "validation", "summary", {
            "before_issues": len(before.issues), "after_issues": len(after.issues),
            "batch_failures": after.batch_failures, "gate": asdict(gate),
        })
        summary.corrected_cells = cleaned.corrected_cells
        summary.gate_outcome = gate.outcome
        summary.accepted = gate.proceeding
        summary.quarantined = gate.counts["quarantine"]
        summary.rejected = gate.counts["reject"]
        batch_id = digest({"source": str(config.source.resolve()), "source_hash": source_hash,
                           "previous": extracted.previous_watermark,
                           "candidate": extracted.candidate_watermark, "policy": config.policy(),
                           "references": reference_hashes})
        quarantine = stage("persist_audit", lambda: self.journal.persist(
            run_id, batch_id, extracted.data, cleaned, dispositions, after.batch_failures
        ))
        if gate.outcome == "stop":
            summary.status = "stopped"
            return summary
        if extracted.data.empty:
            summary.status = "no_new_rows"
            return summary
        positions = [record.row_position for record in dispositions if record.disposition in {"pass", "corrected"}]
        accepted = cleaned.data.iloc[positions].copy()

        def transform():
            if config.transform is None:
                return accepted
            settings = config.transform
            result = BandTransformer(settings["source_column"], settings["derived_column"],
                                     [BandRule(**item) for item in settings["rules"]]).transform(accepted)
            if result[settings["derived_column"]].isna().any():
                raise ValueError("Configured bands do not cover every accepted source value")
            return result

        transformed = stage("transform", transform)
        loaded = stage("load", lambda: self.loader.load(transformed, config.target_table, config.schema))
        summary.inserted, summary.reused = loaded.inserted, loaded.reused

        def reconcile():
            report = self.loader.reconcile(loaded, transformed, config.schema, config.sum_columns)
            accounted = summary.accepted + summary.quarantined + summary.rejected == summary.extracted
            audit_matches = self.journal.verify_quarantine(batch_id, quarantine)
            self.journal.event(run_id, "reconcile", "checks", {
                "checks": [asdict(check) for check in report.checks],
                "rows_accounted_for": accounted, "quarantine_matches": audit_matches,
            })
            if not report.passed or not accounted or not audit_matches:
                raise RuntimeError("Reconciliation failed; progress is withheld")
            if file_digest(config.source) != source_hash:
                raise RuntimeError("Source changed during the run; progress is withheld")
            if any(file_digest(path) != reference_hashes[table] for table, path in config.reference_paths.items()):
                raise RuntimeError("Reference changed during the run; progress is withheld")
            return True

        stage("reconcile", reconcile)
        stage("commit", lambda: self.extractor.commit(config.source, config.watermark_column, extracted))
        summary.status = "succeeded"
        return summary

    def run(self):
        run_id = uuid4().hex
        self.journal.start(run_id, self.config.job_name, self.config.policy())
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                result = self._attempt(run_id, attempt)
                self.journal.finish(run_id, result.status, asdict(result))
                return result
            except Exception as error:
                transient = isinstance(error, OSError) and not isinstance(error, FileNotFoundError)
                if isinstance(error, sqlite3.OperationalError):
                    transient = any(word in str(error).lower() for word in ("locked", "busy"))
                if transient and attempt < self.config.max_attempts:
                    self.journal.event(run_id, "retry", "scheduled", {"attempt": attempt, "error": str(error)})
                    time.sleep(0.05 * attempt)
                    continue
                self.journal.finish(run_id, "failed", {"attempts": attempt}, f"{type(error).__name__}: {error}")
                raise


# The original planning helpers remain available alongside the executable job.
PIPELINE_STAGES = ["extract", "profile", "validate_before", "clean", "validate_after",
                   "classify", "gate", "persist_audit", "transform", "load", "reconcile", "commit"]
RECORD_OUTCOMES = ["PASS", "CORRECTED", "QUARANTINE", "REJECT"]


def stage_plan():
    return PIPELINE_STAGES.copy()


def stop_required(gate_decision):
    from .gates import GateStatus
    return gate_decision.status == GateStatus.STOP
