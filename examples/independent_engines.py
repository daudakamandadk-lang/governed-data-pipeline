"""Use profile, clean and validate independently, without persistent writes."""
from pprint import pprint
import pandas as pd
from governed_data_pipeline.cleaning import CleaningEngine
from governed_data_pipeline.profiling import profile_data
from governed_data_pipeline.validation import validate_fields


def main():
    data = pd.DataFrame({"id": [1, 2, 3], "amount": [" 100 ", "unknown", "-5"]})
    schema = {"primary_key": "id", "columns": {"id": {"dtype": "integer", "required": True},
                                                "amount": {"dtype": "float", "required": True, "min": 0}}}
    pprint(profile_data(data))
    cleaned = CleaningEngine().clean(data, schema)
    print("Original:", data, sep="\n")
    print("Cleaned:", cleaned.data, sep="\n")
    print("Corrections:", cleaned.corrections)
    print("Cleaning issues:", cleaned.issues)
    print("Validation:", validate_fields(cleaned.data, schema))


if __name__ == "__main__":
    main()
