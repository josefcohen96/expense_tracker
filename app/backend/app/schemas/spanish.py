"""Request body for a graded Spanish card (api/spanish.py)."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..services.spanish import item_exists


class SpanishReviewCreate(BaseModel):
    item_id: str = Field(min_length=1, max_length=64)
    grade: int = Field(ge=0, le=3)          # 0 שוב · 1 קשה · 2 טוב · 3 קל (an intro sends 2)
    mode: Literal["intro", "recall"]
    context: Literal["rest", "study"] = "rest"

    @field_validator("item_id")
    @classmethod
    def _known_item(cls, value: str) -> str:
        if not item_exists(value):
            raise ValueError("unknown item_id")
        return value
