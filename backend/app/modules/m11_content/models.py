import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ContentBrief(Base, UUIDMixin, TimestampMixin):
    """
    A structured creative brief entered by the owner or AM.
    Claude uses this to generate content drafts.

    status: draft | generating | ready | submitted | approved | published
    """

    __tablename__ = "content_briefs"

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
    # Optional — links to M5 campaign
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Optional — links to M5 campaign task
    campaign_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaign_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)

    # Brief fields (natural language — fed to Claude)
    objective: Mapped[str] = mapped_column(
        Text, nullable=False
    )   # What should this content achieve?
    target_audience: Mapped[str | None] = mapped_column(Text)
    key_message: Mapped[str | None] = mapped_column(Text)
    tone_of_voice: Mapped[str | None] = mapped_column(
        String(100)
    )   # professional | casual | witty | urgent | inspirational
    platform: Mapped[str] = mapped_column(
        String(50), default="instagram"
    )   # instagram | facebook | google_ads | email | linkedin
    content_type: Mapped[str] = mapped_column(
        String(50), default="social_post"
    )   # social_post | ad_copy | email | video_script | carousel
    word_limit: Mapped[int | None] = mapped_column(Integer)
    reference_urls: Mapped[str | None] = mapped_column(Text)   # CSV of URLs
    additional_notes: Mapped[str | None] = mapped_column(Text)

    # How many draft variations to generate
    num_variations: Mapped[int] = mapped_column(Integer, default=3)

    # draft | generating | ready | submitted | approved | published
    status: Mapped[str] = mapped_column(String(30), default="draft")

    # Assigned to (employee who created the brief)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # relationships
    drafts: Mapped[list["ContentDraft"]] = relationship(
        back_populates="brief",
        cascade="all, delete-orphan",
        order_by="ContentDraft.variation_number",
    )

    def __repr__(self) -> str:
        return f"<ContentBrief {self.title[:40]} [{self.status}]>"


class ContentDraft(Base, UUIDMixin, TimestampMixin):
    """
    A single AI-generated draft variation for a ContentBrief.
    One brief can have multiple variations (default 3).

    status: generated | selected | submitted | approved | rejected | published
    """

    __tablename__ = "content_drafts"

    brief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_briefs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Which variation (1, 2, 3...)
    variation_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # The generated content
    headline: Mapped[str | None] = mapped_column(String(500))
    body_copy: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str | None] = mapped_column(String(255))    # call to action
    hashtags: Mapped[str | None] = mapped_column(Text)      # space-separated

    # Brief variation label (e.g. "Emotional angle", "Feature-led", "Urgency")
    angle: Mapped[str | None] = mapped_column(String(255))

    # generated | selected | submitted | approved | rejected | published
    status: Mapped[str] = mapped_column(String(30), default="generated")

    # Buffer post ID after publishing
    buffer_post_id: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Client feedback on rejection
    rejection_feedback: Mapped[str | None] = mapped_column(Text)

    # relationship
    brief: Mapped["ContentBrief"] = relationship(back_populates="drafts")
    approval_request: Mapped["ClientApprovalRequest | None"] = relationship(
        back_populates="draft",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ContentDraft v{self.variation_number} "
            f"brief={self.brief_id} [{self.status}]>"
        )


class ClientApprovalRequest(Base, UUIDMixin, TimestampMixin):
    """
    An approval request sent to the client for a specific draft.
    Tracks whether the client approved via portal or WhatsApp.

    status: pending | approved | rejected | expired
    channel: portal | whatsapp | both
    """

    __tablename__ = "client_approval_requests"

    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_drafts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
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

    # pending | approved | rejected | expired
    status: Mapped[str] = mapped_column(String(20), default="pending")

    # portal | whatsapp | both
    sent_via: Mapped[str] = mapped_column(String(20), default="both")

    # Approval/rejection metadata
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    response_channel: Mapped[str | None] = mapped_column(
        String(20)
    )  # portal | whatsapp
    client_feedback: Mapped[str | None] = mapped_column(Text)

    # Follow-up tracking
    reminder_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reminder_count: Mapped[int] = mapped_column(Integer, default=0)

    # relationship
    draft: Mapped["ContentDraft"] = relationship(
        back_populates="approval_request"
    )

    def __repr__(self) -> str:
        return (
            f"<ClientApprovalRequest draft={self.draft_id} "
            f"[{self.status}] via={self.sent_via}>"
        )