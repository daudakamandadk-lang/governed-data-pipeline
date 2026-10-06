"""Compatibility import; prefer governed_data_pipeline.profiling."""
from governed_data_pipeline.profiling import *
import governed_data_pipeline.profiling as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
