"""Schema base classes and shared shapes.

Request and response models are separated deliberately. A request model that
doubles as a response model is how a client ends up able to set `reporter_id`
or `role` by including it in the body.
"""

from __future__ import annotations

from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

# Fields the server owns. A request schema containing any of these is a
# mass-assignment hole; a test asserts none of them do.
SERVER_CONTROLLED_FIELDS = frozenset(
    {
        "id",
        "created_at",
        "updated_at",
        "reporter_id",
        "role",
        "status",
        "password_hash",
        "is_active",
        "acknowledged_at",
        "assigned_at",
        "resolved_at",
        "closed_at",
        "sessions_valid_from",
        "failed_login_count",
        "locked_until",
    }
)

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


class StrictModel(BaseModel):
    """Base for every *request* body.

    `extra="forbid"` turns an unexpected field into a 400 rather than a silent
    no-op. Without it, a client sending `{"role": "Facility Admin"}` to an
    endpoint that ignores it gets a 201 and reasonably assumes it worked -- and
    if any handler later does `Model(**payload)`, it becomes privilege
    escalation.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResponseModel(BaseModel):
    """Base for every response body.

    `from_attributes` lets a route return an ORM object directly.
    """

    model_config = ConfigDict(from_attributes=True)


class PageParams(StrictModel):
    """Offset pagination, applied to every list endpoint.

    Bounded on purpose: an unbounded list is both a performance problem and a
    way to pull an entire table in one request.
    """

    limit: Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE
    offset: Annotated[int, Field(ge=0)] = 0


class Page(ResponseModel, Generic[T]):
    """One page of results, with enough context to render a pager."""

    items: list[T]
    total: int = Field(
        description="Total rows visible to *this caller*, not rows in the table."
    )
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        """Whether another page follows."""
        return self.offset + len(self.items) < self.total
