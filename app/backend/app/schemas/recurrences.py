from typing import Optional
from pydantic import BaseModel

class RecurrenceBase(BaseModel):
    name: str
    amount: float
    category_id: int
    user_id: int
    frequency: str               # "monthly" | "weekly" | "yearly"
    day_of_month: Optional[int] = None
    weekday: Optional[int] = None
    next_charge_date: Optional[str] = None  # ISO date for next due; server sets default
    custom_cron: Optional[str] = None
    account_id: Optional[int] = None
    active: bool = True

class RecurrenceCreate(RecurrenceBase):
    pass

class RecurrenceUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    category_id: Optional[int] = None
    user_id: Optional[int] = None
    frequency: Optional[str] = None
    day_of_month: Optional[int] = None
    weekday: Optional[int] = None
    next_charge_date: Optional[str] = None
    custom_cron: Optional[str] = None
    account_id: Optional[int] = None
    active: Optional[bool] = None

class Recurrence(RecurrenceBase):
    id: int


class RecurrenceApplyOnce(BaseModel):
    date: Optional[str] = None
    amount: Optional[float] = None
    notes: Optional[str] = None