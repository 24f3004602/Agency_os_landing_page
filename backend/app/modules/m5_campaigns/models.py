import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey,
    String, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Campaign(Base, UUIDMixin, TimestampMixin):
    """
    A marketing campaign for a client.
    Groups related CampaignTask deliverables together.

    status: active | paused | completed | cancelled
    """

    __tablename__ = "campaigns"

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

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # e.g. meta | google_ads | email | social | content
    platform: Mapped[str] = mapped_column(String(50), default="social")

    # active | paused | completed | cancelled
    status: Mapped[str] = mapped_column(String(30), default="active")

    start_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Budget allocated to this campaign
    budget: Mapped[str | None] = mapped_column(String(50))

    # relationships
    tasks: Mapped[list["CampaignTask"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="CampaignTask.created_at",
    )

    def __repr__(self) -> str:
        return f"<Campaign {self.name} [{self.status}]>"


class CampaignTask(Base, UUIDMixin, TimestampMixin):
    """
    A single deliverable within a Campaign.
    Could be an ad copy variation, social post, email, blog article, etc.

    Status pipeline:
      brief → in_progress → draft → review → approved → scheduled → live

    When approved:
      - If platform supports scheduling → Buffer API called via n8n
      - Task moves to scheduled
      - When post goes live → M10 begins monitoring performance
    """

    __tablename__ = "campaign_tasks"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # ad_copy | social_post | email | blog | video_script | banner
    content_type: Mapped[str] = mapped_column(String(50), default="social_post")

    # brief → in_progress → draft → review → approved → scheduled → live
    status: Mapped[str] = mapped_column(String(30), default="brief", index=True)

    # The actual content draft produced by the employee
    draft_content: Mapped[str | None] = mapped_column(Text)

    # Client / owner feedback when requesting changes
    feedback: Mapped[str | None] = mapped_column(Text)

    # Scheduling metadata (populated after Buffer scheduling)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    buffer_post_id: Mapped[str | None] = mapped_column(String(255))
    went_live_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Deadline for this specific deliverable
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # relationships
    campaign: Mapped["Campaign"] = relationship(back_populates="tasks")

    def __repr__(self) -> str:
        return f"<CampaignTask {self.title[:40]} [{self.status}]>"