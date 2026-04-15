import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


# Journey stages in order
ABM_STAGES = [
    "identified",
    "researching",
    "first_touch",
    "engaged",
    "proposal",
    "closed_won",
    "closed_lost",
]


class AbmAccount(Base, UUIDMixin, TimestampMixin):
    """
    A high-priority target account being worked through
    the ABM journey. Not necessarily a lead yet — could be
    a cold prospect identified by research.

    stage: identified → researching → first_touch →
           engaged → proposal → closed_won | closed_lost
    """

    __tablename__ = "abm_accounts"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional link to Lead (if lead already exists in M7)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Account details
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str | None] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(100))
    company_size: Mapped[str | None] = mapped_column(String(100))

    # Primary contact at this account
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_linkedin: Mapped[str | None] = mapped_column(String(500))
    contact_phone: Mapped[str | None] = mapped_column(String(50))

    # Journey state
    stage: Mapped[str] = mapped_column(
        String(30), default="identified", index=True
    )

    # AE working this account
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )

    # AI-generated intelligence context
    # Populated from M6 Qdrant search on orchestration
    intelligence_summary: Mapped[str | None] = mapped_column(Text)

    # Last AI-recommended next action
    ai_next_action: Mapped[str | None] = mapped_column(Text)

    # When the last touch was made
    last_touch_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Stage transition timestamps
    stage_entered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # relationships
    touches: Mapped[list["AbmTouch"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        order_by="AbmTouch.touched_at.desc()",
    )
    notes: Mapped[list["AbmAccountNote"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        order_by="AbmAccountNote.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<AbmAccount {self.company_name} [{self.stage}]>"


class AbmTouch(Base, UUIDMixin, TimestampMixin):
    """
    Every interaction with an ABM account.
    Could be outbound (we sent something) or inbound (they responded).

    channel  : email | linkedin | whatsapp | ad | call | meeting | other
    direction: outbound | inbound
    type     : first_contact | follow_up | proposal | content_share | other
    """

    __tablename__ = "abm_touches"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("abm_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # email | linkedin | whatsapp | ad | call | meeting | other
    channel: Mapped[str] = mapped_column(String(30), nullable=False)

    # outbound | inbound
    direction: Mapped[str] = mapped_column(String(20), default="outbound")

    # first_contact | follow_up | proposal | content_share | other
    touch_type: Mapped[str] = mapped_column(String(30), default="other")

    # Content of the touch
    subject: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str | None] = mapped_column(Text)

    # Was this AI-generated or manually written
    ai_generated: Mapped[bool] = mapped_column(
        default=False
    )

    # Outcome of the touch (populated manually or on reply detection)
    # no_response | opened | replied | meeting_booked | proposal_requested
    outcome: Mapped[str | None] = mapped_column(String(50))

    touched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Who executed this touch
    executed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )

    # relationship
    account: Mapped["AbmAccount"] = relationship(back_populates="touches")

    def __repr__(self) -> str:
        return (
            f"<AbmTouch {self.channel} {self.direction} "
            f"account={self.account_id}>"
        )


class AbmAccountNote(Base, UUIDMixin, TimestampMixin):
    """
    Free-text notes added by owner or AE about an account.
    Visible in the account intelligence feed.
    """

    __tablename__ = "abm_account_notes"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("abm_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
    )
    written_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # relationship
    account: Mapped["AbmAccount"] = relationship(back_populates="notes")

    def __repr__(self) -> str:
        return f"<AbmAccountNote account={self.account_id}>"