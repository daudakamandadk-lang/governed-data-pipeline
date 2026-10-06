"""Compatibility import; prefer governed_data_pipeline.values."""
from governed_data_pipeline.values import *
import governed_data_pipeline.values as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
