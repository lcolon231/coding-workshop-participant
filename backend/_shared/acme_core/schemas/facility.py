"""Request and response bodies for buildings, floors, seats and categories."""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import Field

from acme_core.schemas.common import ResponseModel, StrictModel

Code = Annotated[str, Field(min_length=1, max_length=20)]
Name = Annotated[str, Field(min_length=1, max_length=200)]


class BuildingCreate(StrictModel):
    """Create a building."""

    code: Code
    name: Name
    address: Annotated[str | None, Field(max_length=400)] = None


class BuildingUpdate(StrictModel):
    """Update a building; omitted fields are unchanged."""

    name: Annotated[str | None, Field(min_length=1, max_length=200)] = None
    address: Annotated[str | None, Field(max_length=400)] = None
    is_active: bool | None = None


class BuildingOut(ResponseModel):
    """A building."""

    id: uuid.UUID
    code: str
    name: str
    address: str | None
    is_active: bool


class FloorCreate(StrictModel):
    """Create a floor. Levels are signed, because basements exist."""

    building_id: uuid.UUID
    level: int
    name: Annotated[str | None, Field(max_length=100)] = None


class FloorOut(ResponseModel):
    """A floor."""

    id: uuid.UUID
    building_id: uuid.UUID
    level: int
    name: str | None


class SeatCreate(StrictModel):
    """Create a seat."""

    floor_id: uuid.UUID
    code: Code
    label: Annotated[str | None, Field(max_length=100)] = None


class SeatOut(ResponseModel):
    """A seat."""

    id: uuid.UUID
    floor_id: uuid.UUID
    code: str
    label: str | None
    is_active: bool


class CategoryCreate(StrictModel):
    """Create a category, optionally beneath a parent."""

    name: Annotated[str, Field(min_length=1, max_length=100)]
    parent_id: uuid.UUID | None = None
    description: Annotated[str | None, Field(max_length=400)] = None


class CategoryOut(ResponseModel):
    """A category."""

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    description: str | None
    is_active: bool
