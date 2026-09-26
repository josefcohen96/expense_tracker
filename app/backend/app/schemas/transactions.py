from typing import List, Optional
from pydantic import BaseModel

class TransactionBase(BaseModel):
    date: str
    amount: float
    category_id: int
    user_id: int
    account_id: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    recurrence_id: Optional[int] = None
    period_key: Optional[str] = None

class TransactionCreate(TransactionBase):
    pass

class TransactionUpdate(BaseModel):
    date: Optional[str] = None
    amount: Optional[float] = None
    category_id: Optional[int] = None
    user_id: Optional[int] = None
    account_id: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    recurrence_id: Optional[int] = None
    period_key: Optional[str] = None

class Transaction(TransactionBase):
    id: int


# Card statement import (Max xlsx): the rows the user kept in the preview.
class ImportRow(BaseModel):
    date: str
    amount: float  # the statement's charge: positive for a charge, negative for a refund
    merchant: str
    category_id: int

class ImportRequest(BaseModel):
    user_id: int
    account_id: Optional[int] = None
    rows: List[ImportRow]

class ImportUndoRequest(BaseModel):
    ids: List[int]
