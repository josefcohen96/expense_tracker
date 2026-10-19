from pydantic import BaseModel, Field


class TestMessage(BaseModel):
    """A chat line to run through the תרשום grammar without sending anything."""
    text: str = Field(min_length=1, max_length=1000)
