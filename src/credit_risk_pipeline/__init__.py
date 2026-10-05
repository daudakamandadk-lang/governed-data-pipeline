"""Reusable engines and a connected CSV-to-SQLite learning workflow."""
from importlib import import_module

__version__ = "0.2.0"
_EXPORTS = {
    "cleaning": ["CleaningEngine"],
    "extraction": ["ExtractionEngine", "SourceConfig", "SourceType"],
    "gates": ["GateDecision", "GateStatus", "evaluate_gate"],
    "incremental": ["IncrementalFileExtractionEngine", "JsonWatermarkStore"],
    "loading": ["IdempotentSqliteLoader", "ReplayConflict"],
    "pipeline": ["GovernedPipeline", "PipelineConfig", "PipelineRun"],
    "profiling": ["profile_data"],
    "validation": ["validate_fields", "validate_schema"],
}
__all__ = [name for names in _EXPORTS.values() for name in names]


def __getattr__(name):
    for module, names in _EXPORTS.items():
        if name in names:
            value = getattr(import_module("." + module, __name__), name)
            globals()[name] = value
            return value
    raise AttributeError(name)
