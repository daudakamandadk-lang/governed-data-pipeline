"""Compatibility import; prefer governed_data_pipeline.database_pipeline."""
from governed_data_pipeline.database_pipeline import *
import governed_data_pipeline.database_pipeline as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
