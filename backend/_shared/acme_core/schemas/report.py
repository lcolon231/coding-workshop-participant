"""Query parameters and response bodies for the reporting endpoints."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from pydantic import ConfigDict, Field, model_validator

from acme_core.models.enums import Priority
from acme_core.reporting import DEFAULT_RANGE_DAYS, MAX_RANGE_DAYS
from acme_core.schemas.common import ResponseModel, StrictModel


class ReportRange(StrictModel):
    """The window a report covers, inclusive at both ends.

    `from` and `to` are the wire names; `from` is a Python keyword, so the
    attributes are `date_from` and `date_to`. Omitted, the window is the last
    `DEFAULT_RANGE_DAYS` days ending today (UTC).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)

    date_from: dt.date | None = Field(default=None, alias="from")
    date_to: dt.date | None = Field(default=None, alias="to")
    building_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _resolve_and_bound(self) -> ReportRange:
        """Fill the defaults, then refuse a backwards or oversized window."""
        if self.date_to is None:
            self.date_to = dt.datetime.now(dt.UTC).date()
        if self.date_from is None:
            self.date_from = self.date_to - dt.timedelta(days=DEFAULT_RANGE_DAYS - 1)
        if self.date_from > self.date_to:
            raise ValueError("from must not be after to")
        if (self.date_to - self.date_from).days + 1 > MAX_RANGE_DAYS:
            raise ValueError(f"the range may cover at most {MAX_RANGE_DAYS} days")
        return self


class SlaParams(ReportRange):
    """Query parameters for `GET /api/incidents/reports/sla`."""

    group_by: Annotated[str, Field(pattern="^(priority|building|category)$")] = "priority"


class VolumeParams(ReportRange):
    """Query parameters for `GET /api/incidents/reports/volume`."""

    interval: Annotated[str, Field(pattern="^(day|week)$")] = "day"
    group_by: Annotated[str, Field(pattern="^(status|priority|category)$")] = "status"


class CountBucket(ResponseModel):
    """One labelled count. A list of these, not a dict, so order is explicit."""

    key: str
    count: int


class _Window(ResponseModel):
    """The resolved window a report actually covered, echoed back."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    date_from: dt.date = Field(alias="from")
    date_to: dt.date = Field(alias="to")


class SummaryReport(_Window):
    """Counts by status and priority, and how old the open backlog is."""

    total: int
    by_status: list[CountBucket]
    by_priority: list[CountBucket]
    backlog_by_age: list[CountBucket] = Field(
        description="Non-closed incidents by age: <1d, 1-3d, 3-7d, >7d."
    )


class SlaTarget(ResponseModel):
    """The resolution target for one priority, so the chart can draw it."""

    priority: Priority
    target_seconds: int


class SlaRow(ResponseModel):
    """SLA figures for one group. Durations are seconds; null when no data."""

    group: str
    count: int
    resolved_count: int
    mean_ack_seconds: float | None
    p90_ack_seconds: float | None
    mean_resolve_seconds: float | None
    p90_resolve_seconds: float | None
    within_target_ratio: float | None = Field(
        description="Share of resolved incidents resolved within their priority's target."
    )


class SlaReport(_Window):
    """Time-to-acknowledge and time-to-resolve, grouped."""

    group_by: str
    targets: list[SlaTarget]
    rows: list[SlaRow]


class VolumeRow(ResponseModel):
    """Incidents created in one time bucket for one group."""

    bucket_start: dt.date
    group: str
    count: int


class VolumeReport(_Window):
    """Incidents created per interval, for the dashboard charts."""

    interval: str
    group_by: str
    rows: list[VolumeRow]
