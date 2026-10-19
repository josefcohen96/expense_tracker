"""The wedding module's JSON API, one router per feature, exposed as a single router for main.py."""
from fastapi import APIRouter

from . import (
    budget,
    files,
    guests,
    ideas,
    milestones,
    notes,
    overseas,
    rooms,
    seating,
    settings,
    tasks,
    timeline,
    vendors,
)

router = APIRouter()
# Nesting routers is safe here: no wedding API route is @public, so the
# build_public_route_matchers caveat in requirements.txt does not apply.
for _module in (vendors, guests, rooms, tasks, budget, settings, files, notes, ideas, overseas, timeline, milestones, seating):
    router.include_router(_module.router)
