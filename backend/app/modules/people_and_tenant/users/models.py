import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.modules.people_and_tenant.agencies.models import Agency


# ─── Role constants ────────────────────────────────────────────────────────────
class UserRole:
    SUPERADMIN = "superadmin"
    OWNER = "owner"
    EMPLOYEE = "employee"
    CLIENT = "client"


class User(Base, UUIDMixin, TimestampMixin):
    """
    Single users table for all four roles.
    agency_id is NULL only for superadmin.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # UserRole constants
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # NULL for superadmin
    agency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), index=True
    )

    # relationships
    agency: Mapped["Agency | None"] = relationship(back_populates="users")
    employee_profile: Mapped["Employee | None"] = relationship(
        back_populates="user", uselist=False
    )
    client_profile: Mapped["Client | None"] = relationship(
        back_populates="user", uselist=False
    )

    def __repr__(self) -> str:
        return f"<User {self.email} [{self.role}]>"


class Employee(Base, UUIDMixin, TimestampMixin):
    """
    Extended profile for users with role=employee.
    Stores compensation and employment details.
    """

    __tablename__ = "employees"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    designation: Mapped[str | None] = mapped_column(String(255))

    # compensation
    compensation_type: Mapped[str] = mapped_column(String(20), default="fixed")  # fixed | hourly
    compensation_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    # monthly salary if fixed, hourly rate if hourly

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # relationships
    user: Mapped["User"] = relationship(back_populates="employee_profile")

    def __repr__(self) -> str:
        return f"<Employee user={self.user_id} agency={self.agency_id}>"


class Client(Base, UUIDMixin, TimestampMixin):
    """
    Agency clients — companies the agency works for.
    user_id is populated once the client activates their portal account.
    """

    __tablename__ = "clients"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional — only populated if client has portal access
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50))

    # status: active | at_risk | paused | churned
    status: Mapped[str] = mapped_column(String(50), default="active")

    # account manager (employee)
    account_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )

    # HubSpot integration
    hubspot_deal_id: Mapped[str | None] = mapped_column(String(100), index=True)
    hubspot_contact_id: Mapped[str | None] = mapped_column(String(100))

    notes: Mapped[str | None] = mapped_column(Text)

    # relationships
    user: Mapped["User | None"] = relationship(back_populates="client_profile")

    def __repr__(self) -> str:
        return f"<Client {self.company_name} agency={self.agency_id}>"
