from typing import List
from pydantic import BaseModel

class BackupItem(BaseModel):
    file: str
    size: int
    created: str

class BackupList(BaseModel):
    backups: List[BackupItem]
