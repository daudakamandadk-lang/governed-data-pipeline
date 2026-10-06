"""Compatibility import; prefer governed_data_pipeline.quality_reports."""
from governed_data_pipeline.quality_reports import *
import governed_data_pipeline.quality_reports as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
