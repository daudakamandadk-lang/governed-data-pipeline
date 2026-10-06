"""Compatibility import; prefer governed_data_pipeline.chunked."""
from governed_data_pipeline.chunked import *
import governed_data_pipeline.chunked as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
