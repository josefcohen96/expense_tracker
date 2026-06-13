from pydantic import BaseModel
from typing import List

class WorkoutExerciseSchema(BaseModel):
    exercise_name: str
    total_sets: int
    total_reps: int

class WorkoutCreateSchema(BaseModel):
    date: str
    workout_type: str
    total_duration: int  # in minutes
    exercises: List[WorkoutExerciseSchema]
