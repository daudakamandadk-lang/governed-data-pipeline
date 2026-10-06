"""Compatibility import; prefer governed_data_pipeline.gates."""
from governed_data_pipeline.gates import *
import governed_data_pipeline.gates as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
