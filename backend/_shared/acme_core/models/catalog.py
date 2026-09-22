"""Incident categories."""

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from acme_core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What an incident is about, as a two-level tree.

    Self-referential rather than a fixed two-table split, so "Workplace
    Technology > Monitor" and "Facilities > HVAC" share one shape and new
    branches need no migration.
    """

    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    parent: Mapped[Optional["Category"]] = relationship(
        back_populates="children", remote_side="Category.id"
    )
    children: Mapped[list["Category"]] = relationship(back_populates="parent")

    __table_args__ = (
        # Sibling names must differ; the same leaf name under two parents is fine.
        UniqueConstraint("parent_id", "name", name="uq_categories_parent_id_name"),
    )

    def __repr__(self) -> str:
        """Return a short representation."""
        return f"<Category {self.name!r}>"
