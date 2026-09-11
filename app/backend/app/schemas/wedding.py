"""
Pydantic schemas for the wedding module.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


# ─── Vendors ────────────────────────────────────────────────────────────────

class VendorCreate(BaseModel):
    name: str
    category: str
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    price_quoted: Optional[float] = None
    what_included: Optional[str] = None
    status: str = "not_contacted"
    deposit_amount: Optional[float] = None
    deposit_paid_date: Optional[str] = None
    notes: Optional[str] = None
    instagram_url: Optional[str] = None
    facebook_url: Optional[str] = None
    location: Optional[str] = None
    inclusions: Optional[str] = None


class VendorUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    price_quoted: Optional[float] = None
    what_included: Optional[str] = None
    status: Optional[str] = None
    deposit_amount: Optional[float] = None
    deposit_paid_date: Optional[str] = None
    notes: Optional[str] = None
    instagram_url: Optional[str] = None
    facebook_url: Optional[str] = None
    location: Optional[str] = None
    inclusions: Optional[str] = None


class QuoteItem(BaseModel):
    id: Optional[int] = None
    description: str
    quantity: float = 1
    unit_price: float = 0
    apply_vat: int = 1
    sort_order: int = 0


# ─── Guests ─────────────────────────────────────────────────────────────────

class GuestCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    group_name: Optional[str] = None
    status: str = "pending"
    plus_one: int = 0
    plus_one_name: Optional[str] = None
    children_count: int = 0
    needs_transport: int = 0
    staying_overnight: int = 0
    table_number: Optional[int] = None
    notes: Optional[str] = None
    meal_type: str = "regular"
    food_notes: Optional[str] = None
    plus_one_meal_type: str = "regular"


class GuestUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    group_name: Optional[str] = None
    status: Optional[str] = None
    plus_one: Optional[int] = None
    plus_one_name: Optional[str] = None
    children_count: Optional[int] = None
    needs_transport: Optional[int] = None
    staying_overnight: Optional[int] = None
    table_number: Optional[int] = None
    notes: Optional[str] = None
    meal_type: Optional[str] = None
    food_notes: Optional[str] = None
    plus_one_meal_type: Optional[str] = None


# ─── Rooms ───────────────────────────────────────────────────────────────────

class RoomCreate(BaseModel):
    name: str
    room_type: str = "יחידים"
    max_capacity: int = 2
    notes: Optional[str] = None


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    room_type: Optional[str] = None
    max_capacity: Optional[int] = None
    notes: Optional[str] = None


# ─── Tasks ───────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str
    category: str = "general"
    due_date: Optional[str] = None
    priority: str = "medium"
    notes: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[str] = None
    completed: Optional[int] = None
    priority: Optional[str] = None
    notes: Optional[str] = None


# ─── Budget ──────────────────────────────────────────────────────────────────

class BudgetItemCreate(BaseModel):
    name: str
    category: str = "other"
    budgeted_amount: float = 0
    actual_amount: float = 0
    notes: Optional[str] = None


class BudgetItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    budgeted_amount: Optional[float] = None
    actual_amount: Optional[float] = None
    notes: Optional[str] = None


# ─── Settings ────────────────────────────────────────────────────────────────

class SettingUpsert(BaseModel):
    key: str
    value: str


# ─── Notes ───────────────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    title: str
    content: Optional[str] = None
    color: str = "white"
    pinned: int = 0


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    color: Optional[str] = None
    pinned: Optional[int] = None


# ─── Ideas ───────────────────────────────────────────────────────────────────

class IdeaCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str = "כללי"
    status: str = "new"
    color: str = "white"


class IdeaUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    color: Optional[str] = None


# ─── Timeline ────────────────────────────────────────────────────────────────

class TimelineEventCreate(BaseModel):
    day: str
    title: str
    description: Optional[str] = None
    start_time: str
    end_time: Optional[str] = None
    category: str = "general"


class TimelineEventUpdate(BaseModel):
    day: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    category: Optional[str] = None


# ─── Seating ─────────────────────────────────────────────────────────────────

class SeatingTableCreate(BaseModel):
    name: str
    shape: str = "round"
    capacity: int = 8
    x: float = 100
    y: float = 100
    color: str = "rose"
    notes: Optional[str] = None


class SeatingTableUpdate(BaseModel):
    name: Optional[str] = None
    shape: Optional[str] = None
    capacity: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None
    color: Optional[str] = None
    notes: Optional[str] = None


class SeatingTablePositions(BaseModel):
    tables: list  # [{id, x, y}]


class SeatingAssign(BaseModel):
    table_id: int
    seat_number: int
    guest_id: int
    extra_seats: list[int] = []
