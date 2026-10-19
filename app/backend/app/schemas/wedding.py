"""
Pydantic schemas for the wedding module.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

# ─── Vendors ────────────────────────────────────────────────────────────────

class VendorCreate(BaseModel):
    name: str
    category: str
    contact_name: str | None = None
    phone: str | None = None
    price_quoted: float | None = None
    what_included: str | None = None
    status: str = "not_contacted"
    deposit_amount: float | None = None
    deposit_paid_date: str | None = None
    notes: str | None = None
    instagram_url: str | None = None
    facebook_url: str | None = None
    location: str | None = None
    inclusions: str | None = None
    portions_ordered: int | None = Field(default=None, ge=0)


class VendorUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    contact_name: str | None = None
    phone: str | None = None
    price_quoted: float | None = None
    what_included: str | None = None
    status: str | None = None
    deposit_amount: float | None = None
    deposit_paid_date: str | None = None
    notes: str | None = None
    instagram_url: str | None = None
    facebook_url: str | None = None
    location: str | None = None
    inclusions: str | None = None
    portions_ordered: int | None = Field(default=None, ge=0)


class QuoteItem(BaseModel):
    id: int | None = None
    description: str
    quantity: float = 1
    unit_price: float = 0
    apply_vat: int = 1
    sort_order: int = 0


# ─── Guests ─────────────────────────────────────────────────────────────────

class GuestCreate(BaseModel):
    name: str
    phone: str | None = None
    group_name: str | None = None
    status: str = "pending"
    plus_one: int = 0
    plus_one_name: str | None = None
    children_count: int = 0
    needs_transport: int = 0
    staying_overnight: int = 0
    table_number: int | None = None
    notes: str | None = None
    meal_type: str = "regular"
    food_notes: str | None = None
    plus_one_meal_type: str = "regular"


class GuestUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    group_name: str | None = None
    status: str | None = None
    plus_one: int | None = None
    plus_one_name: str | None = None
    children_count: int | None = None
    needs_transport: int | None = None
    staying_overnight: int | None = None
    table_number: int | None = None
    notes: str | None = None
    meal_type: str | None = None
    food_notes: str | None = None
    plus_one_meal_type: str | None = None


# ─── Rooms ───────────────────────────────────────────────────────────────────

class RoomCreate(BaseModel):
    name: str
    room_type: str = "יחידים"
    max_capacity: int = 2
    notes: str | None = None


class RoomUpdate(BaseModel):
    name: str | None = None
    room_type: str | None = None
    max_capacity: int | None = None
    notes: str | None = None


# ─── Tasks ───────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str
    category: str = "general"
    due_date: str | None = None
    priority: str = "medium"
    notes: str | None = None
    owner: str | None = None  # users.name of the household member; None = unassigned


class TaskUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    due_date: str | None = None
    completed: int | None = None
    priority: str | None = None
    notes: str | None = None
    owner: str | None = None


# ─── Budget ──────────────────────────────────────────────────────────────────

class BudgetItemCreate(BaseModel):
    name: str
    category: str = "other"
    budgeted_amount: float = 0
    actual_amount: float = 0
    notes: str | None = None


class BudgetItemUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    budgeted_amount: float | None = None
    actual_amount: float | None = None
    notes: str | None = None


# ─── Settings ────────────────────────────────────────────────────────────────

class SettingUpsert(BaseModel):
    key: str
    value: str


# ─── Notes ───────────────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    title: str
    content: str | None = None
    color: str = "white"
    pinned: int = 0


class NoteUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    color: str | None = None
    pinned: int | None = None


# ─── Ideas ───────────────────────────────────────────────────────────────────

class IdeaCreate(BaseModel):
    title: str
    description: str | None = None
    category: str = "כללי"
    status: str = "new"
    color: str = "white"


class IdeaUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    status: str | None = None
    color: str | None = None


# ─── Overseas orders (הזמנות מחו״ל) ──────────────────────────────────────────

class OverseasItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    url: str | None = None
    store: str | None = Field(default=None, max_length=100)
    sample_price: float | None = Field(default=None, ge=0)
    quantity_needed: int | None = Field(default=None, ge=0)
    created_by: str | None = None  # users.name; defaults to the session user


class OverseasItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = None
    store: str | None = Field(default=None, max_length=100)
    sample_price: float | None = Field(default=None, ge=0)
    quantity_needed: int | None = Field(default=None, ge=0)
    stage: str | None = None


class OverseasCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    author: str | None = None  # users.name; defaults to the session user


# ─── Timeline ────────────────────────────────────────────────────────────────

class TimelineEventCreate(BaseModel):
    day: str
    title: str
    description: str | None = None
    start_time: str
    end_time: str | None = None
    category: str = "general"


class TimelineEventUpdate(BaseModel):
    day: str | None = None
    title: str | None = None
    description: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    category: str | None = None


# ─── Milestones ──────────────────────────────────────────────────────────────

class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    offset_days: int = Field(ge=-1000, le=365)
    kind: str = "general"


class MilestoneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    offset_days: int | None = Field(default=None, ge=-1000, le=365)
    completed: int | None = None
    # YYYY-MM-DD pins the milestone to a day; null returns it to its offset.
    custom_date: str | None = None


# ─── Seating ─────────────────────────────────────────────────────────────────

class SeatingTableCreate(BaseModel):
    name: str
    shape: str = "round"
    capacity: int = 8
    x: float = 100
    y: float = 100
    color: str = "rose"
    notes: str | None = None


class SeatingTableUpdate(BaseModel):
    name: str | None = None
    shape: str | None = None
    capacity: int | None = None
    x: float | None = None
    y: float | None = None
    color: str | None = None
    notes: str | None = None


class SeatingTablePositions(BaseModel):
    tables: list  # [{id, x, y}]


class SeatingAssign(BaseModel):
    table_id: int
    seat_number: int
    guest_id: int
    extra_seats: list[int] = []
