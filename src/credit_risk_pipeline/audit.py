"""Compatibility import; prefer governed_data_pipeline.audit."""
from governed_data_pipeline.audit import *
import governed_data_pipeline.audit as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
