import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Agency(Base, UUIDMixin, TimestampMixin):
    """
    One row per paying agency (tenant).
    agency_id is the partition key for all tenant data.
    """

    __tablename__ = "agencies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_phone: Mapped[str | None] = mapped_column(String(50))

    # billing / lifecycle
    plan_tier: Mapped[str] = mapped_column(
        String(50), default="trial"
    )  # trial | starter | pro | enterprise
    status: Mapped[str] = mapped_column(
        String(50), default="trial"
    )  # active | trial | suspended | churned
    trial_end_date: Mapped[date | None] = mapped_column(Date)
    billing_status: Mapped[str] = mapped_column(
        String(50), default="pending"
    )  # paid | pending | overdue

    # metadata
    notes: Mapped[str | None] = mapped_column(Text)

    # relationships
    modules: Mapped[list["AgencyModule"]] = relationship(
        back_populates="agency", cascade="all, delete-orphan"
    )
    users: Mapped[list["User"]] = relationship(  # noqa: F821
        back_populates="agency", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Agency {self.name} [{self.status}]>"


# All 11 modules as constants — used in AgencyModule.module_code
MODULES = {
    "M1": "Workforce Intelligence",
    "M2": "Operations Core",
    "M3": "Insights & Reporting Agent",
    "M4": "Churn Prevention Agent",
    "M5": "Campaign Task Manager",
    "M6": "Research Agent",
    "M7": "Lead Analyst Agent",
    "M8": "Personalisation & Outreach Agent",
    "M9": "ABM Orchestrator",
    "M10": "Optimisation & Prediction Engine",
    "M11": "Campaign Orchestration Platform",
}

MODULE_DEPENDENCIES: dict[str, list[str]] = {
    "M1": [],
    "M2": ["M1"],
    "M3": ["M2"],
    "M4": ["M3"],
    "M5": ["M2"],
    "M6": ["M2"],
    "M7": ["M2"],
    "M8": ["M6", "M7"],
    "M9": ["M8"],
    "M10": ["M3", "M5"],
    "M11": ["M5", "M10"],
}


class AgencyModule(Base, UUIDMixin, TimestampMixin):
    """
    Which modules are active for which agency.
    One row per (agency, module) pair.
    """

    __tablename__ = "agency_modules"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False
    )
    module_code: Mapped[str] = mapped_column(String(10), nullable=False)  # M1 … M11
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by: Mapped[str | None] = mapped_column(String(255))  # superadmin email

    # relationship
    agency: Mapped["Agency"] = relationship(back_populates="modules")

    def __repr__(self) -> str:
        return f"<AgencyModule {self.module_code} agency={self.agency_id} active={self.is_active}>"
