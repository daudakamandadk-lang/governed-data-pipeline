"""Compatibility namespace; new code uses governed_data_pipeline."""
import governed_data_pipeline as _implementation
__version__ = _implementation.__version__
__all__ = _implementation.__all__

def __getattr__(name):
    if name == "CleaningEngine":
        from .cleaning import CleaningEngine
        return CleaningEngine
    return getattr(_implementation, name)
