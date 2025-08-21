from pydantic import BaseModel
from typing import Optional
from datetime import datetime

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
