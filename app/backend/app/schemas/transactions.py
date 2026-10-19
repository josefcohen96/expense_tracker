
from pydantic import BaseModel


class TransactionBase(BaseModel):
    date: str
    amount: float
    category_id: int
    user_id: int
    account_id: int | None = None
    notes: str | None = None
    tags: str | None = None
    recurrence_id: int | None = None
    period_key: str | None = None

class TransactionCreate(TransactionBase):
    pass

class TransactionUpdate(BaseModel):
    date: str | None = None
    amount: float | None = None
    category_id: int | None = None
    user_id: int | None = None
    account_id: int | None = None
    notes: str | None = None
    tags: str | None = None
    recurrence_id: int | None = None
    period_key: str | None = None

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
    account_id: int | None = None
    rows: list[ImportRow]

class ImportUndoRequest(BaseModel):
    ids: list[int]
