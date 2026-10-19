
from pydantic import BaseModel


class RecurrenceBase(BaseModel):
    name: str
    amount: float
    category_id: int
    user_id: int
    frequency: str               # "monthly" | "weekly" | "yearly"
    day_of_month: int | None = None
    weekday: int | None = None
    next_charge_date: str | None = None  # ISO date for next due; server sets default
    account_id: int | None = None
    active: bool = True

class RecurrenceCreate(RecurrenceBase):
    pass

class RecurrenceUpdate(BaseModel):
    name: str | None = None
    amount: float | None = None
    category_id: int | None = None
    user_id: int | None = None
    frequency: str | None = None
    day_of_month: int | None = None
    weekday: int | None = None
    next_charge_date: str | None = None
    account_id: int | None = None
    active: bool | None = None

class Recurrence(RecurrenceBase):
    id: int


class RecurrenceApplyOnce(BaseModel):
    date: str | None = None
    amount: float | None = None
    notes: str | None = None