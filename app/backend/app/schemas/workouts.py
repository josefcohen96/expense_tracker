from pydantic import BaseModel
from typing import Dict, List, Optional

class WorkoutExerciseSchema(BaseModel):
    exercise_name: str
    total_sets: int
    total_reps: int
    # Best single set, for personal records
    max_reps: Optional[int] = None
    # Quest station this exercise trained (SKILL_PROGRESSIONS key + progression index)
    skill_key: Optional[str] = None
    stage_index: Optional[int] = None

class WorkoutCreateSchema(BaseModel):
    date: str
    workout_type: str
    total_duration: int  # in minutes
    exercises: List[WorkoutExerciseSchema]

class WorkoutLegacyProgressSchema(BaseModel):
    # skill_key -> stage indexes a browser had marked "conquered" by hand
    progress: Dict[str, List[int]]
