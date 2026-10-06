"""Compatibility import; prefer governed_data_pipeline.transformation."""
from governed_data_pipeline.transformation import *
import governed_data_pipeline.transformation as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
