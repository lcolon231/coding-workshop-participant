"""Column helpers shared by the model modules."""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum

# Comfortably longer than the longest member ("Facility Admin").
_ENUM_LENGTH = 32


def enum_type(enum_cls: type[StrEnum]) -> SAEnum:
    """Build a VARCHAR-backed column type for a StrEnum.

    `native_enum=False` emits VARCHAR instead of a PostgreSQL ENUM, and
    `create_constraint=True` is required with it -- SQLAlchemy defaults that to
    False, which would leave an unconstrained VARCHAR accepting any string. And
    `values_callable` stores the member *value* ("Facility Admin") rather than
    its name ("FACILITY_ADMIN"), so rows read naturally in psql and in a CSV
    export.

    Args:
        enum_cls: The enumeration to store.

    Returns:
        A SQLAlchemy type for use in `mapped_column`.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=_ENUM_LENGTH,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )
