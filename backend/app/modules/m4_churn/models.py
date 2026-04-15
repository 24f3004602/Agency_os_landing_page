import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ChurnAlert(Base, UUIDMixin, TimestampMixin):
    """
    Created when a client's churn risk score crosses the alert threshold.
    One alert per detection event — a client can have multiple alerts
    across different periods.

    status: open | resolved | false_positive
    """

    __tablename__ = "churn_alerts"

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

    # 0.0 – 100.0
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)

    # JSON string — list of signal descriptions that contributed to score
    # e.g. ["ROAS dropped from 3.1 to 1.8", "No inbound messages in 14 days"]
    trigger_reasons_json: Mapped[str] = mapped_column(Text, default="[]")

    # Claude's suggested retention actions (JSON list of strings)
    retention_actions_json: Mapped[str] = mapped_column(Text, default="[]")

    # Competitor context from M6 if available
    competitor_context: Mapped[str | None] = mapped_column(Text)

    # open | resolved | false_positive
    status: Mapped[str] = mapped_column(String(20), default="open")

    # Populated when owner resolves
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution_note: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return (
            f"<ChurnAlert client={self.client_id} "
            f"score={self.risk_score} status={self.status}>"
        )