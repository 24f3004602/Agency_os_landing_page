import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, Float,
    ForeignKey, Integer, String, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class IcpProfile(Base, UUIDMixin, TimestampMixin):
    """
    The agency's Ideal Client Profile definition.
    One per agency — upserted via API.

    Claude uses this to score incoming leads 0-100.
    Fields are plain text descriptions so the owner
    can define them in natural language.
    """

    __tablename__ = "icp_profiles"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,    # one ICP per agency
        index=True,
    )

    # Natural language descriptions of ideal client
    ideal_industries: Mapped[str] = mapped_column(
        Text,
        default="D2C brands, e-commerce, retail, food & beverage",
    )
    ideal_company_size: Mapped[str] = mapped_column(
        Text,
        default="10-500 employees, Series A to Series C startups",
    )
    ideal_ad_budget: Mapped[str] = mapped_column(
        Text,
        default="Monthly ad spend of ₹2L to ₹50L",
    )
    ideal_decision_maker: Mapped[str] = mapped_column(
        Text,
        default="Founder, CMO, Marketing Head, Growth Manager",
    )
    ideal_pain_points: Mapped[str] = mapped_column(
        Text,
        default=(
            "Struggling with ROAS, want to scale paid ads, "
            "unhappy with current agency, need data-driven approach"
        ),
    )
    disqualifiers: Mapped[str] = mapped_column(
        Text,
        default=(
            "Budget under ₹1L/month, B2B SaaS without marketing budget, "
            "looking only for SEO, no product-market fit yet"
        ),
    )

    # Score threshold above which a lead is considered high-priority
    high_priority_threshold: Mapped[int] = mapped_column(
        Integer, default=70
    )

    def __repr__(self) -> str:
        return f"<IcpProfile agency={self.agency_id}>"


class Lead(Base, UUIDMixin, TimestampMixin):
    """
    An inbound or manually entered potential client.
    Scored by the Lead Analyst Agent against the agency's ICP.

    source: manual | hubspot | typeform | linkedin | referral
    status: new | scored | contacted | qualified | disqualified | converted
    """

    __tablename__ = "leads"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Contact info
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    designation: Mapped[str | None] = mapped_column(String(255))

    # Company info
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_size: Mapped[str | None] = mapped_column(String(100))
    industry: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(255))
    monthly_ad_budget: Mapped[str | None] = mapped_column(String(100))

    # Pain points and notes captured on intake
    pain_points: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    # Source tracking
    source: Mapped[str] = mapped_column(String(50), default="manual")
    hubspot_deal_id: Mapped[str | None] = mapped_column(String(100), index=True)
    hubspot_contact_id: Mapped[str | None] = mapped_column(String(100))

    # Status
    # new | scored | contacted | qualified | disqualified | converted
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)

    # Assigned account executive (employee)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )

    # relationship
    score: Mapped["LeadScore | None"] = relationship(
        back_populates="lead",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Lead {self.full_name} at {self.company_name} [{self.status}]>"


class LeadScore(Base, UUIDMixin, TimestampMixin):
    """
    Claude's ICP scoring result for a lead.
    One-to-one with Lead — updated on each re-score.

    score      : 0-100
    rationale  : Claude's explanation
    next_action: specific suggested action for the AE
    """

    __tablename__ = "lead_scores"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    score: Mapped[float] = mapped_column(Float, nullable=False)

    # Why Claude scored them this way
    rationale: Mapped[str | None] = mapped_column(Text)

    # Strengths (JSON list of strings)
    strengths_json: Mapped[str] = mapped_column(Text, default="[]")

    # Concerns (JSON list of strings)
    concerns_json: Mapped[str] = mapped_column(Text, default="[]")

    # What the AE should do next
    next_action: Mapped[str | None] = mapped_column(Text)

    # Was this written back to HubSpot
    hubspot_updated: Mapped[bool] = mapped_column(Boolean, default=False)

    # relationship
    lead: Mapped["Lead"] = relationship(back_populates="score")

    def __repr__(self) -> str:
        return f"<LeadScore lead={self.lead_id} score={self.score}>"