"""Compatibility import; prefer governed_data_pipeline.loading."""
from governed_data_pipeline.loading import *
import governed_data_pipeline.loading as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
