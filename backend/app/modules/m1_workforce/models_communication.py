import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class CommunicationLog(Base, UUIDMixin, TimestampMixin):
    """
    Every message between an employee and a client.
    Written on send (outbound) and on webhook/polling receipt (inbound).

    direction : outbound (employee → client) | inbound (client → employee)
    channel   : email | whatsapp
    status    : sent | delivered | failed | received
    is_flagged: True if the nightly audit agent flagged this message
    flag_reason: Claude's explanation of why it was flagged
    """

    __tablename__ = "communication_logs"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,   # NULL for inbound (no employee sent it)
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # outbound | inbound
    direction: Mapped[str] = mapped_column(String(20), nullable=False)

    # email | whatsapp
    channel: Mapped[str] = mapped_column(String(20), nullable=False)

    subject: Mapped[str | None] = mapped_column(String(500))  # email only
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # sent | delivered | failed | received
    status: Mapped[str] = mapped_column(String(20), default="sent")

    # External IDs for deduplication
    gmail_message_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    wati_message_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )

    # Audit agent fields — populated by nightly Claude scan
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    flag_reason: Mapped[str | None] = mapped_column(Text)
    flag_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    flag_reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<CommunicationLog {self.direction} via {self.channel} "
            f"client={self.client_id} flagged={self.is_flagged}>"
        )