import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer,
    Numeric, String, Text, Float
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class GeofenceZone(Base, UUIDMixin, TimestampMixin):
    """
    Owner-defined office/work location.
    Clock-ins are validated against all active zones for the agency.
    """

    __tablename__ = "geofence_zones"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g. "Main Office"
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    radius_metres: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    # relationships
    sessions: Mapped[list["AttendanceSession"]] = relationship(back_populates="zone")

    def __repr__(self) -> str:
        return f"<GeofenceZone {self.name} ({self.latitude},{self.longitude}) r={self.radius_metres}m>"


class AttendanceSession(Base, UUIDMixin, TimestampMixin):
    """
    One row per clock-in event.
    clock_out_time and hours_worked are NULL until clock-out.
    status: open | complete | incomplete (flagged by Celery at EOD)
    """

    __tablename__ = "attendance_sessions"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Geofence zone matched on clock-in (NULL = remote / override)
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("geofence_zones.id", ondelete="SET NULL"),
        nullable=True,
    )

    # GPS captured at clock-in
    clock_in_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    clock_in_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    clock_in_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Populated on clock-out
    clock_out_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hours_worked: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True
    )

    # open → complete (clocked out) | incomplete (flagged by Celery)
    status: Mapped[str] = mapped_column(String(20), default="open")

    # Notes — owner can add a note to incomplete sessions
    notes: Mapped[str | None] = mapped_column(Text)

    # relationships
    zone: Mapped["GeofenceZone | None"] = relationship(back_populates="sessions")

    def __repr__(self) -> str:
        return (
            f"<AttendanceSession emp={self.employee_id} "
            f"in={self.clock_in_time} status={self.status}>"
        )
