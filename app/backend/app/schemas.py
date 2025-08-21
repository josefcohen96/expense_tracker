from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime

# Original schemas
class Transaction(BaseModel):
    id: int
    date: str
    amount: float
    category_id: Optional[int]
    user_id: Optional[int]
    account_id: Optional[int]
    notes: Optional[str]
    tags: Optional[str]
    recurrence_id: Optional[int]
    period_key: Optional[str]

class TransactionCreate(BaseModel):
    date: str
    amount: float
    category_id: Optional[int] = None
    user_id: Optional[int] = None
    account_id: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    recurrence_id: Optional[int] = None
    period_key: Optional[str] = None

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

class Recurrence(BaseModel):
    id: int
    name: str
    amount: float
    category_id: int
    user_id: int
    frequency: str
    start_date: str
    end_date: Optional[str]
    day_of_month: Optional[int]
    weekday: Optional[int]
    active: bool

class RecurrenceCreate(BaseModel):
    name: str
    amount: float
    category_id: int
    user_id: int
    frequency: str
    start_date: str
    end_date: Optional[str] = None
    day_of_month: Optional[int] = None
    weekday: Optional[int] = None

class RecurrenceUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    category_id: Optional[int] = None
    user_id: Optional[int] = None
    frequency: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    day_of_month: Optional[int] = None
    weekday: Optional[int] = None
    active: Optional[bool] = None

# Challenge schemas
class Challenge(BaseModel):
    id: int
    name: str
    description: str
    category: str
    target_value: float
    target_period: str
    points: int
    difficulty: str
    is_active: bool
    created_at: datetime

class ChallengeCreate(BaseModel):
    name: str
    description: str
    category: str
    target_value: float
    target_period: str
    points: int = 10
    difficulty: str = "bronze"

class UserChallenge(BaseModel):
    id: int
    user_id: int
    challenge_id: int
    current_progress: float
    target_value: float
    start_date: str
    end_date: str
    status: str
    completed_at: Optional[str]
    points_earned: int

class UserChallengeCreate(BaseModel):
    user_id: int
    challenge_id: int
    target_value: float
    start_date: str
    end_date: str

class ChallengeProgress(BaseModel):
    id: int
    user_challenge_id: int
    progress_date: str
    progress_value: float
    notes: Optional[str]

class ChallengeProgressCreate(BaseModel):
    user_challenge_id: int
    progress_value: float
    notes: Optional[str] = None

class UserPoints(BaseModel):
    id: int
    user_id: int
    total_points: int
    current_level: str
    level_progress: int
    last_updated: datetime

class ChallengeStatus(BaseModel):
    challenge: Challenge
    user_challenge: Optional[UserChallenge]
    progress_percentage: float
    days_remaining: int
    is_completed: bool
    is_failed: bool
