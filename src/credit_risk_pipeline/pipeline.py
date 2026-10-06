"""Compatibility import; prefer governed_data_pipeline.pipeline."""
from governed_data_pipeline.pipeline import *
import governed_data_pipeline.pipeline as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
