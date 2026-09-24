"""Request and response bodies for engineer profiles.

Profiles are created with their user (`POST /api/auth/users`) and live as long
as it does, so there is no create schema here: only reading, filtering and
editing the scheduling fields.
"""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import Field

from acme_core.schemas.auth import EngineerProfileOut, Specialty, UserSummary
from acme_core.schemas.common import Order, PageParams, UpdateModel

# An engineer carrying more than this at once is a data-entry error, not a
# workload; the bound stops a typo from making someone look permanently free.
MAX_CONCURRENT_LIMIT = 50


class EngineerOut(EngineerProfileOut):
    """A profile with its user and current load, for the assignment picker."""

    user: UserSummary
    open_assignments: int = Field(
        description="Incidents assigned to this engineer that are not yet Resolved or Closed."
    )


class EngineerFilters(PageParams):
    """Query parameters for the engineer list."""

    specialty: Annotated[str | None, Field(max_length=100)] = None
    is_available: bool | None = None
    sort: Annotated[
        str, Field(pattern="^(full_name|specialty|open_assignments)$")
    ] = "full_name"
    order: Order = "asc"


class EngineerProfileUpdate(UpdateModel):
    """Edit an engineer's scheduling data. Omitted fields are unchanged."""

    CLEARABLE: ClassVar[frozenset[str]] = frozenset()

    specialty: Specialty | None = None
    max_concurrent_incidents: Annotated[
        int | None, Field(ge=1, le=MAX_CONCURRENT_LIMIT)
    ] = None
    is_available: bool | None = None
