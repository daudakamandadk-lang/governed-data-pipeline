"""Reusable engines and a connected CSV-to-SQLite learning workflow."""
from importlib import import_module

__version__ = "0.3.0"
_EXPORTS = {
    "cleaning": ["CleaningEngine"],
    "extraction": ["ExtractionEngine", "SourceConfig", "SourceType"],
    "gates": ["GateDecision", "GateStatus", "evaluate_gate", "evaluate_score_gate"],
    "record_gates": ["GateThresholds", "evaluate_record_gate"],
    "incremental": ["IncrementalFileExtractionEngine", "JsonWatermarkStore"],
    "loading": ["IdempotentSqliteLoader", "ReplayConflict"],
    "profiling": ["profile_data"],
    "validation": ["validate_fields", "validate_schema"],
    "sqlite_source": ["ReadOnlySqliteExtractor", "CompositeCursorResult"],
    "sqlite_cdc": ["SqliteChangeCapture", "ChangeEvent"],
    "sqlite_change_loader": ["SqliteChangeLoader"],
    "database_pipeline": ["DatabaseJobConfig", "DatabaseRun", "SqliteDatabasePipeline"],
    "pipeline": ["GovernedPipeline", "PipelineConfig", "PipelineRun", "RunFinalizationError"],
}
__all__ = [name for names in _EXPORTS.values() for name in names]


def __getattr__(name):
    for module, names in _EXPORTS.items():
        if name in names:
            value = getattr(import_module("." + module, __name__), name)
            globals()[name] = value
            return value
    raise AttributeError(name)
