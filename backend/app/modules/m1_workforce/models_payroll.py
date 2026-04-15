import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class PayrollRun(Base, UUIDMixin, TimestampMixin):
    """
    One payroll run per agency per calendar month.
    Owner triggers → system calculates → owner approves → PDFs generated.

    Status flow: draft → approved
    Once approved, the run is locked — no changes allowed.
    """

    __tablename__ = "payroll_runs"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Pay period — e.g. month=4, year=2026 means April 2026
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)

    # draft | approved
    status: Mapped[str] = mapped_column(String(20), default="draft")

    # Totals across all employees — populated on calculation
    total_gross: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    total_net: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    total_employees: Mapped[int] = mapped_column(Integer, default=0)

    # Approval
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text)

    # relationships
    payslips: Mapped[list["Payslip"]] = relationship(
        back_populates="payroll_run",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<PayrollRun {self.period_month}/{self.period_year} "
            f"agency={self.agency_id} status={self.status}>"
        )


class Payslip(Base, UUIDMixin, TimestampMixin):
    """
    One payslip per employee per PayrollRun.
    Stores the full pay breakdown and path to the generated PDF.
    """

    __tablename__ = "payslips"

    payroll_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payroll_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
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

    # Pay calculation inputs
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    days_present: Mapped[int] = mapped_column(Integer, default=0)
    hours_worked: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"))

    # Pay breakdown
    gross_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    deductions: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    allowances: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    net_pay: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    # PDF — stored as a file path relative to media root
    # e.g. "payslips/2026/04/emp_uuid.pdf"
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text)

    # relationship
    payroll_run: Mapped["PayrollRun"] = relationship(back_populates="payslips")

    def __repr__(self) -> str:
        return (
            f"<Payslip emp={self.employee_id} "
            f"{self.period_month}/{self.period_year} net={self.net_pay}>"
        )