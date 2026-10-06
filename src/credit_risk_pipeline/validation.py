"""Compatibility import; prefer governed_data_pipeline.validation."""
from governed_data_pipeline.validation import *
import governed_data_pipeline.validation as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
