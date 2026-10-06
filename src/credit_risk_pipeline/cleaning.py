"""Legacy cleaner defaults; new code uses governed_data_pipeline.cleaning."""
from governed_data_pipeline.cleaning import *
import governed_data_pipeline.cleaning as _implementation


class CleaningEngine(_implementation.CleaningEngine):
    """Retain the first lesson's one-argument applicant-ID normalization."""

    def clean(self, data, schema=None, date_formats=None):
        if schema is None:
            if "applicant_id" not in data.columns:
                raise ValueError("Required column missing from input: applicant_id")
            schema = {"columns": {"applicant_id": {"dtype": "string"}}}
        return super().clean(data, schema, date_formats)


def __getattr__(name):
    return getattr(_implementation, name)
