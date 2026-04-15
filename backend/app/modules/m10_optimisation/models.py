import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class OptimisationConfig(Base, UUIDMixin, TimestampMixin):
    """
    Per-client optimisation settings.
    Controls whether the agent operates in advisory or autonomous mode,
    and what guardrails apply in autonomous mode.
    """

    __tablename__ = "optimisation_configs"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # advisory | autonomous
    mode: Mapped[str] = mapped_column(String(20), default="advisory")

    # Autonomous mode guardrails
    # Maximum % change allowed per day for budgets
    max_budget_change_pct: Mapped[float] = mapped_column(Float, default=20.0)
    # Maximum % change allowed per day for bids
    max_bid_change_pct: Mapped[float] = mapped_column(Float, default=15.0)
    # Minimum daily budget (₹) — never go below this
    min_daily_budget: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("500")
    )

    # Kill switch — owner can disable autonomous execution instantly
    autonomous_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Which change types are approved for autonomous execution
    # JSON list: ["pause_ad", "adjust_bid", "reallocate_budget"]
    approved_change_types_json: Mapped[str] = mapped_column(
        Text, default='["pause_ad"]'
    )

    # KPI targets for gap analysis
    target_roas: Mapped[float | None] = mapped_column(Float)
    target_ctr: Mapped[float | None] = mapped_column(Float)
    target_cpc: Mapped[float | None] = mapped_column(Float)

    def __repr__(self) -> str:
        return (
            f"<OptimisationConfig client={self.client_id} mode={self.mode}>"
        )


class OptimisationRun(Base, UUIDMixin, TimestampMixin):
    """
    One analysis cycle per client.
    Contains the raw performance data and list of recommendations.

    status: analysing → recommendations_ready → approved → executing → complete | failed
    """

    __tablename__ = "optimisation_runs"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # analysing → recommendations_ready → approved → executing → complete | failed
    status: Mapped[str] = mapped_column(
        String(30), default="analysing"
    )

    # Mode at time of run (copied from config)
    mode: Mapped[str] = mapped_column(String(20), default="advisory")

    # Raw performance snapshot (JSON)
    performance_snapshot_json: Mapped[str | None] = mapped_column(Text)

    # Summary of analysis (natural language)
    analysis_summary: Mapped[str | None] = mapped_column(Text)

    # How many recommendations generated / approved / executed
    total_recommendations: Mapped[int] = mapped_column(Integer, default=0)
    approved_count: Mapped[int] = mapped_column(Integer, default=0)
    executed_count: Mapped[int] = mapped_column(Integer, default=0)

    error_message: Mapped[str | None] = mapped_column(Text)

    # relationships
    recommendations: Mapped[list["OptimisationRecommendation"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="OptimisationRecommendation.confidence_score.desc()",
    )

    def __repr__(self) -> str:
        return (
            f"<OptimisationRun client={self.client_id} "
            f"status={self.status} recs={self.total_recommendations}>"
        )


class OptimisationRecommendation(Base, UUIDMixin, TimestampMixin):
    """
    A single actionable recommendation from an OptimisationRun.

    change_type: pause_ad | adjust_bid | reallocate_budget |
                 pause_adset | scale_budget | change_creative
    status: pending | approved | rejected | executing | executed | failed
    """

    __tablename__ = "optimisation_recommendations"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("optimisation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # What type of change
    # pause_ad | adjust_bid | reallocate_budget | pause_adset | scale_budget
    change_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Platform: meta | google_ads
    platform: Mapped[str] = mapped_column(String(30), nullable=False)

    # The entity being changed (ad ID, adset ID, campaign ID)
    entity_id: Mapped[str | None] = mapped_column(String(255))
    entity_name: Mapped[str | None] = mapped_column(String(500))

    # The specific change in plain English
    # e.g. "Reduce daily budget from ₹5,000 to ₹4,000"
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Current value and proposed value
    current_value: Mapped[str | None] = mapped_column(String(100))
    proposed_value: Mapped[str | None] = mapped_column(String(100))

    # Claude's confidence 0-100
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)

    # Why Claude recommends this
    rationale: Mapped[str | None] = mapped_column(Text)

    # pending | approved | rejected | executing | executed | failed
    status: Mapped[str] = mapped_column(String(20), default="pending")

    # Execution details
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    execution_result: Mapped[str | None] = mapped_column(Text)

    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # relationship
    run: Mapped["OptimisationRun"] = relationship(back_populates="recommendations")

    def __repr__(self) -> str:
        return (
            f"<OptimisationRecommendation {self.change_type} "
            f"{self.platform} [{self.status}] conf={self.confidence_score}>"
        )


class PredictiveAlert(Base, UUIDMixin, TimestampMixin):
    """
    Alert generated when trajectory analysis predicts
    a client will miss their KPI targets by end of month.

    severity: warning | critical
    status  : open | acknowledged | resolved
    """

    __tablename__ = "predictive_alerts"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # warning | critical
    severity: Mapped[str] = mapped_column(String(20), default="warning")

    # open | acknowledged | resolved
    status: Mapped[str] = mapped_column(String(20), default="open")

    # Which KPI is at risk
    kpi_name: Mapped[str] = mapped_column(String(50))  # roas | ctr | cpc | conversions

    # Current trajectory vs target
    current_value: Mapped[float | None] = mapped_column(Float)
    target_value: Mapped[float | None] = mapped_column(Float)
    projected_eom_value: Mapped[float | None] = mapped_column(Float)

    # Gap as percentage
    gap_percentage: Mapped[float | None] = mapped_column(Float)

    # Claude's suggested corrective action
    suggested_action: Mapped[str | None] = mapped_column(Text)

    # Days remaining in month when alert was raised
    days_remaining: Mapped[int | None] = mapped_column(Integer)

    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<PredictiveAlert {self.kpi_name} {self.severity} "
            f"client={self.client_id} [{self.status}]>"
        )