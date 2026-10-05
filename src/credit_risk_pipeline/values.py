"""Small scalar/JSON helpers shared by the learning audit and database stages."""

from datetime import date, datetime
import hashlib
import json
import math

import pandas as pd


def missing(value):
    if isinstance(value, str):
        return not value.strip()
    return pd.api.types.is_scalar(value) and bool(pd.isna(value))


def audit_value(value):
    if isinstance(value, str):
        return value  # Audit history must preserve even blank original text.
    if isinstance(value, dict):
        return {str(key): audit_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [audit_value(item) for item in value]
    if missing(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": str(value)}
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    return {"type": type(value).__name__, "value": str(value)}


def json_text(value):
    return json.dumps(audit_value(value), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(json_text(value).encode("utf-8")).hexdigest()


def file_digest(path):
    checksum = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()
