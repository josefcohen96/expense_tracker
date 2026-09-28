from pydantic import BaseModel, Field


class PushKeysSchema(BaseModel):
    p256dh: str = Field(min_length=1)
    auth: str = Field(min_length=1)


class PushSubscriptionSchema(BaseModel):
    """The browser's `PushSubscription.toJSON()` (extra fields like expirationTime are ignored)."""
    endpoint: str = Field(min_length=1)
    keys: PushKeysSchema


class PushUnsubscribeSchema(BaseModel):
    endpoint: str = Field(min_length=1)
