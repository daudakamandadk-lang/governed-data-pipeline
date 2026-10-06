"""Compatibility import; prefer governed_data_pipeline.extraction."""
from governed_data_pipeline.extraction import *
import governed_data_pipeline.extraction as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
