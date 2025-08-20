from typing import Optional
from pydantic import BaseModel

class RecurrenceBase(BaseModel):
    name: str
    amount: float
    category_id: int
    user_id: int
    start_date: str
    end_date: Optional[str] = None
    frequency: str               # "monthly" | "weekly" | "yearly"
    day_of_month: Optional[int] = None
    weekday: Optional[int] = None
    custom_cron: Optional[str] = None
    account_id: Optional[int] = None
    active: bool = True

class RecurrenceCreate(RecurrenceBase):
    pass

class Recurrence(RecurrenceBase):
    id: int
