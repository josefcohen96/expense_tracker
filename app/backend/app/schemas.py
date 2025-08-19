"""Pydantic schemas defining request and response models.

These classes serve as the data models for incoming API
requests and outgoing responses. They validate and document the
structure of data flowing through the FastAPI endpoints.
"""

from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, Field, validator


class User(BaseModel):
    id: int
    name: str
    is_active: bool = True

    class Config:
        from_attributes = True


class Category(BaseModel):
    id: int
    name: str
    type: str
    color: Optional[str] = None

    class Config:
        from_attributes = True


class Account(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


class RecurrenceBase(BaseModel):
    name: str
    amount: float
    category_id: int = Field(..., description="Identifier of the category")
    user_id: int = Field(..., description="Identifier of the user")
    start_date: str = Field(..., description="Start date in YYYY-MM-DD format")
    end_date: Optional[str] = Field(None, description="End date in YYYY-MM-DD format or null")
    frequency: str = Field(..., description="Frequency: monthly, weekly, yearly or custom")
    day_of_month: Optional[int] = Field(None, description="Day of month for monthly recurrences (1-31)")
    weekday: Optional[int] = Field(None, description="Weekday for weekly recurrences (0=Monday)")
    custom_cron: Optional[str] = Field(None, description="Custom cron expression (optional)")
    account_id: Optional[int] = Field(None, description="Payment account ID")
    active: bool = Field(True, description="Whether the recurrence is active")

    @validator("frequency")
    def validate_frequency(cls, v: str) -> str:
        allowed = {"monthly", "weekly", "yearly", "custom"}
        if v not in allowed:
            raise ValueError(f"Frequency must be one of {allowed}")
        return v


class RecurrenceCreate(RecurrenceBase):
    pass


class Recurrence(RecurrenceBase):
    id: int

    class Config:
        from_attributes = True


class TransactionBase(BaseModel):
    date: str = Field(..., description="Date of the transaction (YYYY-MM-DD)")
    amount: float = Field(..., description="Amount (negative for expense, positive for income)")
    category_id: int = Field(..., description="Category identifier")
    user_id: int = Field(..., description="User identifier")
    account_id: Optional[int] = Field(None, description="Account identifier")
    notes: Optional[str] = Field(None, description="Free text notes")
    tags: Optional[str] = Field(None, description="Comma separated tags")
    recurrence_id: Optional[int] = Field(None, description="Associated recurrence ID")
    period_key: Optional[str] = Field(None, description="Unique period key for recurring transactions")


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

    class Config:
        from_attributes = True


class BackupItem(BaseModel):
    file_name: str
    size: int
    created_at: str


class BackupList(BaseModel):
    backups: List[BackupItem]