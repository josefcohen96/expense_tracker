from typing import Optional
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
