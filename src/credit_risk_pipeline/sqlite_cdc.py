"""Compatibility import; prefer governed_data_pipeline.sqlite_cdc."""
from governed_data_pipeline.sqlite_cdc import *
import governed_data_pipeline.sqlite_cdc as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
