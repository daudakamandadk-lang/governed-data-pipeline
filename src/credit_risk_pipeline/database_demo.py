"""Compatibility import; prefer governed_data_pipeline.database_demo."""
from governed_data_pipeline.database_demo import *
import governed_data_pipeline.database_demo as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
