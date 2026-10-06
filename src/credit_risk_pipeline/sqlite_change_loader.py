"""Compatibility import; prefer governed_data_pipeline.sqlite_change_loader."""
from governed_data_pipeline.sqlite_change_loader import *
import governed_data_pipeline.sqlite_change_loader as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
