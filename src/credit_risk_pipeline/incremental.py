"""Compatibility import; prefer governed_data_pipeline.incremental."""
from governed_data_pipeline.incremental import *
import governed_data_pipeline.incremental as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
