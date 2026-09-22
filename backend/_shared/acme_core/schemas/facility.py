"""Request and response bodies for buildings, floors, seats and categories."""

from __future__ import annotations

import uuid
from typing import Annotated, ClassVar

from pydantic import Field, model_validator

from acme_core.schemas.common import Order, PageParams, ResponseModel, StrictModel, UpdateModel

Code = Annotated[str, Field(min_length=1, max_length=20)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Address = Annotated[str, Field(max_length=400)]
FloorName = Annotated[str, Field(max_length=100)]
SeatLabel = Annotated[str, Field(max_length=100)]
CategoryName = Annotated[str, Field(min_length=1, max_length=100)]
Description = Annotated[str, Field(max_length=400)]
Search = Annotated[str | None, Field(max_length=200)]


class _RetirableListing(PageParams):
    """Filters shared by every list of things that can be deactivated.

    `include_inactive` is honoured for admins only; for anyone else the service
    ignores it, so an employee's incident form never offers a retired seat.
    """

    search: Search = None
    include_inactive: bool = False


class BuildingCreate(StrictModel):
    """Create a building."""

    code: Code
    name: Name
    address: Address | None = None


class BuildingUpdate(UpdateModel):
    """Update a building; omitted fields are unchanged.

    `code` is absent: it is printed on signage and asset tags, so renaming it
    would silently invalidate the physical world.
    """

    CLEARABLE: ClassVar[frozenset[str]] = frozenset({"address"})

    name: Name | None = None
    address: Address | None = None
    is_active: bool | None = None


class BuildingFilters(_RetirableListing):
    """Query parameters for the building list. `search` matches code or name."""

    sort: Annotated[str, Field(pattern="^(code|name|created_at)$")] = "code"
    order: Order = "asc"


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
    name: FloorName | None = None


class FloorUpdate(UpdateModel):
    """Update a floor. Moving it to another building is not supported."""

    CLEARABLE: ClassVar[frozenset[str]] = frozenset({"name"})

    level: int | None = None
    name: FloorName | None = None


class FloorFilters(PageParams):
    """Query parameters for a building's floors. Floors cannot be deactivated."""

    sort: Annotated[str, Field(pattern="^(level|name)$")] = "level"
    order: Order = "asc"


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
    label: SeatLabel | None = None


class SeatUpdate(UpdateModel):
    """Update a seat. Moving it to another floor is not supported."""

    CLEARABLE: ClassVar[frozenset[str]] = frozenset({"label"})

    code: Code | None = None
    label: SeatLabel | None = None
    is_active: bool | None = None


class SeatFilters(_RetirableListing):
    """Query parameters for a floor's seats. `search` matches code or label."""

    sort: Annotated[str, Field(pattern="^(code|label)$")] = "code"
    order: Order = "asc"


class SeatOut(ResponseModel):
    """A seat."""

    id: uuid.UUID
    floor_id: uuid.UUID
    code: str
    label: str | None
    is_active: bool


class CategoryCreate(StrictModel):
    """Create a category, optionally beneath a parent.

    The tree has two levels. Whether `parent_id` names a root is a database
    question, so the service enforces it; this schema only shapes the input.
    """

    name: CategoryName
    parent_id: uuid.UUID | None = None
    description: Description | None = None


class CategoryUpdate(UpdateModel):
    """Update a category. Re-parenting is not supported."""

    CLEARABLE: ClassVar[frozenset[str]] = frozenset({"description"})

    name: CategoryName | None = None
    description: Description | None = None
    is_active: bool | None = None


class CategoryFilters(_RetirableListing):
    """Query parameters for the category list.

    Returned flat; the client builds the tree from `parent_id`.
    """

    parent_id: uuid.UUID | None = None
    roots_only: bool = False
    sort: Annotated[str, Field(pattern="^(name)$")] = "name"
    order: Order = "asc"

    @model_validator(mode="after")
    def _one_level_at_a_time(self) -> CategoryFilters:
        """Children of a parent and roots only are contradictory."""
        if self.roots_only and self.parent_id is not None:
            raise ValueError("roots_only and parent_id cannot be combined")
        return self


class CategoryOut(ResponseModel):
    """A category."""

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    description: str | None
    is_active: bool
