"""Physical locations: buildings, floors and seats."""

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from acme_core.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Building(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A site that incidents can be reported against."""

    __tablename__ = "buildings"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    floors: Mapped[list["Floor"]] = relationship(
        back_populates="building", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return a short representation."""
        return f"<Building {self.code!r} {self.name!r}>"


class Floor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One level of a building."""

    __tablename__ = "floors"

    building_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False
    )
    # Signed: basements are negative.
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    building: Mapped["Building"] = relationship(back_populates="floors")
    seats: Mapped[list["Seat"]] = relationship(
        back_populates="floor", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # A building cannot have two level 3s.
        UniqueConstraint("building_id", "level", name="uq_floors_building_id_level"),
    )

    def __repr__(self) -> str:
        """Return a short representation."""
        return f"<Floor building={self.building_id} level={self.level}>"


class Seat(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A desk or workstation on a floor.

    Optional on an incident: a lobby, a lift or a toilet has no seat, which is
    why `incidents.seat_id` is nullable while `building_id` is not.
    """

    __tablename__ = "seats"

    floor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("floors.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    floor: Mapped["Floor"] = relationship(back_populates="seats")

    __table_args__ = (
        # Seat codes repeat between floors; they must not repeat within one.
        UniqueConstraint("floor_id", "code", name="uq_seats_floor_id_code"),
    )

    def __repr__(self) -> str:
        """Return a short representation."""
        return f"<Seat floor={self.floor_id} code={self.code!r}>"
