
from pydantic import BaseModel, Field


class WorkoutExerciseSchema(BaseModel):
    exercise_name: str
    total_sets: int
    total_reps: int
    # Best single set, for personal records
    max_reps: int | None = None
    # Quest station this exercise trained (SKILL_PROGRESSIONS key + progression index)
    skill_key: str | None = None
    stage_index: int | None = None

class WorkoutCreateSchema(BaseModel):
    date: str
    workout_type: str
    total_duration: int  # in minutes
    exercises: list[WorkoutExerciseSchema]

class WorkoutLegacyProgressSchema(BaseModel):
    # skill_key -> stage indexes a browser had marked "conquered" by hand
    progress: dict[str, list[int]]


# ---- admin screen (/workouts/admin) ----

class WorkoutAdminExerciseSchema(BaseModel):
    """One exercise row of a session. `id` keeps an existing row; None inserts a new one."""
    id: int | None = None
    exercise_name: str = Field(min_length=1, max_length=200)
    total_sets: int = Field(ge=0, le=100)
    total_reps: int = Field(ge=0, le=5000)
    max_reps: int | None = Field(default=None, ge=0, le=5000)
    skill_key: str | None = None
    stage_index: int | None = None


class WorkoutSessionWriteSchema(BaseModel):
    """A whole session in one write: its details plus every exercise row it holds."""
    user_id: int
    date: str
    workout_type: str = Field(min_length=1, max_length=50)
    total_duration: int = Field(ge=0, le=1440)
    exercises: list[WorkoutAdminExerciseSchema]


class WorkoutLegacyProgressWriteSchema(BaseModel):
    """Replaces a user's imported "conquered by hand" flags — an empty dict clears them."""
    user_id: int
    progress: dict[str, list[int]] = Field(default_factory=dict)
