"""Learning prototype: standalone CSV chunk extraction.

Row positions are zero-based parsed data rows, not physical CSV line numbers.
Validation/read errors raise when the generator is iterated.
"""

from dataclasses import dataclass,field
from enum import Enum
from pathlib import Path
from typing import Any
import pandas as pd

class SourceType(str,Enum):
    CSV="csv"

class ExtractionStatus(str,Enum):
    SUCCESS="SUCCESS"
    FAILED="FAILED"

@dataclass
class ChunkSourceConfig:
    source_type:SourceType
    path:str
    chunk_size:int=50000
    options:dict[str,Any]=field(default_factory=dict)

@dataclass
class ExtractionChunk:
    status:ExtractionStatus
    chunk_number:int
    data:pd.DataFrame|None
    row_count:int
    start_row:int
    end_row:int
    errors:list[str]=field(default_factory=list)

class ChunkedFileExtractionEngine:
    def validate_source(self,config):
        path=Path(config.path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if not path.is_file():
            raise ValueError(f"Source is not a file: {path}")

        if config.source_type!=SourceType.CSV:
            raise ValueError("Chunked engine currently supports CSV only.")

        if config.chunk_size<=0:
            raise ValueError("chunk_size must be greater than 0.")

        return path

    def extract(self,config):
        path=self.validate_source(config)

        with pd.read_csv(
            path,
            chunksize=config.chunk_size,
            **config.options
        ) as reader:
            start_row=0

            for chunk_number,data in enumerate(reader,start=1):
                if data.empty:
                    continue
                row_count=len(data)
                end_row=start_row+row_count-1

                yield ExtractionChunk(
                    status=ExtractionStatus.SUCCESS,
                    chunk_number=chunk_number,
                    data=data,
                    row_count=row_count,
                    start_row=start_row,
                    end_row=end_row
                )

                start_row=end_row+1
