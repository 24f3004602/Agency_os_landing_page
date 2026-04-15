import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Task(Base, UUIDMixin, TimestampMixin):
    """
    A task dispatched by an owner to an employee.
    Optionally linked to a client.

    Status flow:
      created → in_progress → submitted → verified
                                       ↘ rejected → in_progress
    """

    __tablename__ = "tasks"

    agency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agencies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_to: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,  # preserved even if owner account deleted
    )
    # Optional — links task to a specific client
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # low | medium | high | urgent
    priority: Mapped[str] = mapped_column(String(20), default="medium")

    # created | in_progress | submitted | verified | rejected | overdue
    status: Mapped[str] = mapped_column(String(30), default="created", index=True)

    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Populated by owner when rejecting — shown to employee
    rejection_comment: Mapped[str | None] = mapped_column(Text)

    # relationships
    history: Mapped[list["TaskStatusHistory"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskStatusHistory.changed_at",
    )

    def __repr__(self) -> str:
        return f"<Task {self.title[:40]} [{self.status}] priority={self.priority}>"


class TaskStatusHistory(Base, UUIDMixin):
    """
    Immutable log of every status change on a task.
    Written on every status transition — never updated, never deleted.
    """

    __tablename__ = "task_status_history"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)  # rejection notes etc
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # relationship back to task
    task: Mapped["Task"] = relationship(back_populates="history")

    def __repr__(self) -> str:
        return (
            f"<TaskStatusHistory task={self.task_id} "
            f"{self.from_status}→{self.to_status}>"
        )