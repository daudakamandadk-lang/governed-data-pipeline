"""Compatibility import; prefer governed_data_pipeline.dq."""
from governed_data_pipeline.dq import *
import governed_data_pipeline.dq as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
