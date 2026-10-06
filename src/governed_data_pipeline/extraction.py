"""Prototype for the Phase 2 extraction engine.

The module demonstrates a typed, file-based extraction boundary that returns
both data and extraction metadata. It is intentionally kept as a prototype
until execution, tests and edge-case handling are complete.

No production credentials or private data sources are embedded here.
"""

from dataclasses import dataclass,field
from enum import Enum
from pathlib import Path
from typing import Any
import pandas as pd

# Source types
class SourceType(str,Enum):
    CSV="csv"
    JSON="json"
    EXCEL="excel"
    PARQUET="parquet"

# Extraction status
class ExtractionStatus(str,Enum):
    SUCCESS="SUCCESS"
    FAILED="FAILED"

# Input configuration
@dataclass
class SourceConfig:
    source_type:SourceType
    path:str
    options:dict[str,Any]=field(default_factory=dict)

# Extraction metadata
@dataclass
class ExtractionMetadata:
    source_name:str
    row_count:int
    column_count:int
    columns:list[str]

# Standard extraction result
@dataclass
class ExtractionResult:
    status:ExtractionStatus
    data:pd.DataFrame|None
    metadata:ExtractionMetadata|None
    errors:list[str]=field(default_factory=list)

# Extraction engine
class ExtractionEngine:
    def __init__(self):
        self.readers={
            SourceType.CSV:pd.read_csv,
            SourceType.JSON:pd.read_json,
            SourceType.EXCEL:pd.read_excel,
            SourceType.PARQUET:pd.read_parquet
        }

    def validate_source(self,config):
        path=Path(config.path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return path

    def build_metadata(self,path,data):
        return ExtractionMetadata(
            source_name=path.name,
            row_count=len(data),
            column_count=len(data.columns),
            columns=data.columns.tolist()
        )

    def extract(self,config):
        try:
            path=self.validate_source(config)
            reader=self.readers[config.source_type]
            data=reader(path,**config.options)
            metadata=self.build_metadata(path,data)
            return ExtractionResult(
                status=ExtractionStatus.SUCCESS,
                data=data,
                metadata=metadata
            )
        except Exception as error:
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                data=None,
                metadata=None,
                errors=[str(error)]
            )

# Mental model
# SourceConfig
#   -> validate_source()
#   -> choose reader
#   -> read data
#   -> build_metadata()
#   -> ExtractionResult
