"""One way to page, sort and count a list query.

Every list endpoint returns `Page[T]` with a `total`. Computing that total from
the *same* statement as the items -- after scoping and filtering, before
ordering and slicing -- is what guarantees it counts only rows this caller may
see. A separately written count query is how a list ends up reporting "12
results" while showing an employee three.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from acme_core.schemas.common import PageParams

T = TypeVar("T")


def paginate(
    session: Session,
    statement: Select[Any],
    params: PageParams,
    *,
    sort_columns: Mapping[str, ColumnElement[Any]],
    sort: str,
    order: str,
    tiebreaker: ColumnElement[Any],
) -> tuple[list[Any], int]:
    """Count, order and slice a select.

    Args:
        session: The request's session.
        statement: A fully scoped and filtered select, not yet ordered.
        params: The caller's limit and offset.
        sort_columns: The allowlist mapping each sort key to a column. The key
            has already been validated by the schema's pattern; looking it up
            here means a key that somehow slipped through raises KeyError
            rather than reaching ORDER BY as text.
        sort: The requested sort key.
        order: `asc` or `desc`.
        tiebreaker: A unique column appended to the ordering, so rows that
            share a sort value keep a stable order and no row appears on two
            pages or on none.

    Returns:
        The page of rows and the total number of matching rows.
    """
    total = session.execute(
        select(func.count()).select_from(statement.order_by(None).subquery())
    ).scalar_one()

    column = sort_columns[sort]
    ordering = column.desc() if order == "desc" else column.asc()
    rows = (
        session.execute(
            statement.order_by(ordering, tiebreaker).limit(params.limit).offset(params.offset)
        )
        .scalars()
        .unique()
        .all()
    )
    return list(rows), total


def like_pattern(term: str) -> str:
    """Build a case-insensitive substring pattern with wildcards escaped.

    Without escaping, a search for `50%` or `a_b` matches far more than the
    user typed, and `%` alone matches everything.

    Args:
        term: The user's search text.

    Returns:
        A pattern for `ilike(..., escape="\\\\")`.
    """
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
