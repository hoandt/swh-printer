from typing import Optional
from dataclasses import dataclass

@dataclass
class PrintJob:
    job_id: str
    file_url: str
    document_type: Optional[str] = None