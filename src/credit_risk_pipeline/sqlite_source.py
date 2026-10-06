"""Compatibility import; prefer governed_data_pipeline.sqlite_source."""
from governed_data_pipeline.sqlite_source import *
import governed_data_pipeline.sqlite_source as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
