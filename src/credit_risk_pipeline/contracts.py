"""Compatibility import; prefer governed_data_pipeline.contracts."""
from governed_data_pipeline.contracts import *
import governed_data_pipeline.contracts as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
