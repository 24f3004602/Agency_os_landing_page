import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class TrackedCompetitor(Base, UUIDMixin, TimestampMixin):
    """
    A competitor brand that the agency tracks for a specific client.
    One row per (client, competitor) pair.

    meta_page_id : Facebook/Meta page ID — used to query Meta Ad Library
    domain       : Competitor's website domain — used for SerpAPI queries
    """

    __tablename__ = "tracked_competitors"

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

    competitor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255))      # e.g. "zomato.com"
    meta_page_id: Mapped[str | None] = mapped_column(String(100)) # e.g. "123456789"

    # Industry vertical — used to contextualise Claude's analysis
    industry: Mapped[str | None] = mapped_column(String(100))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # relationships
    briefs: Mapped[list["ResearchBrief"]] = relationship(
        back_populates="competitor",
        cascade="all, delete-orphan",
        order_by="ResearchBrief.created_at.desc()",
    )

    def __repr__(self) -> str:
        return (
            f"<TrackedCompetitor {self.competitor_name} "
            f"client={self.client_id}>"
        )


class ResearchBrief(Base, UUIDMixin, TimestampMixin):
    """
    A Claude-generated competitive intelligence brief
    for one competitor in one research run.

    Stored in PostgreSQL (structured) and Qdrant (vectorised for retrieval).
    The qdrant_point_id links to the vector in Qdrant so M4 and M8
    can retrieve relevant context via semantic search.
    """

    __tablename__ = "research_briefs"

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
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracked_competitors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    competitor_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Raw data from APIs (JSON strings)
    meta_ads_data_json: Mapped[str | None] = mapped_column(Text)
    serp_data_json: Mapped[str | None] = mapped_column(Text)

    # Claude's synthesis
    brief_text: Mapped[str | None] = mapped_column(Text)

    # Key findings as JSON list of strings
    # e.g. ["Competitor launched 3 new video ads", "Increased spend estimate +40%"]
    key_findings_json: Mapped[str] = mapped_column(Text, default="[]")

    # Qdrant vector ID — links to stored embedding
    qdrant_point_id: Mapped[str | None] = mapped_column(String(100))

    # Whether this brief has been acted on (owner marked it)
    acted_on: Mapped[bool] = mapped_column(Boolean, default=False)

    # relationship
    competitor: Mapped["TrackedCompetitor"] = relationship(back_populates="briefs")

    def __repr__(self) -> str:
        return (
            f"<ResearchBrief {self.competitor_name} "
            f"client={self.client_id}>"
        )