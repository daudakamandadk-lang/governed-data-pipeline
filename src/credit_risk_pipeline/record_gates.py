"""Compatibility import; prefer governed_data_pipeline.record_gates."""
from governed_data_pipeline.record_gates import *
import governed_data_pipeline.record_gates as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
