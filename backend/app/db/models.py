"""Core relational models for SIM Classroom Companion.

Business rules and state transitions belong in domain services, not ORM hooks.
All persisted timestamps are timezone-aware; application services store UTC instants.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def enum_type(enum_class: type[Enum], name: str) -> SAEnum:
    """Store enum values as readable strings rather than Python member names."""
    return SAEnum(
        enum_class,
        name=name,
        native_enum=False,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class SchoolRole(str, Enum):
    COORDINATOR = "coordinator"


class ClassRole(str, Enum):
    TEACHER = "teacher"
    STUDENT = "student"


class MembershipStatus(str, Enum):
    ACTIVE = "active"
    INVITED = "invited"
    INACTIVE = "inactive"


class InviteStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class AssignmentTargetType(str, Enum):
    CLASS = "class"
    INDIVIDUAL = "individual"
    GROUP = "group"


class AssignmentStatus(str, Enum):
    DRAFT = "draft"
    ASSIGNED = "assigned"
    CANCELLED = "cancelled"


class RecipientStatus(str, Enum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    SUBMITTED = "submitted"
    NEEDS_REVISION = "needs_revision"
    COMPLETED = "completed"


class ReminderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class School(TimestampMixin, Base):
    __tablename__ = "schools"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SchoolMembership(TimestampMixin, Base):
    __tablename__ = "school_memberships"
    __table_args__ = (
        UniqueConstraint("school_id", "user_id", name="uq_school_membership_school_user"),
        Index("ix_school_memberships_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[SchoolRole] = mapped_column(
        enum_type(SchoolRole, "school_role"), nullable=False
    )
    status: Mapped[MembershipStatus] = mapped_column(
        enum_type(MembershipStatus, "school_membership_status"),
        nullable=False,
        default=MembershipStatus.ACTIVE,
    )


class Classroom(TimestampMixin, Base):
    __tablename__ = "classrooms"
    __table_args__ = (
        UniqueConstraint("school_id", "name", name="uq_classrooms_school_name"),
        Index("ix_classrooms_school_id", "school_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    grade_label: Mapped[str | None] = mapped_column(String(80))


class ClassMembership(TimestampMixin, Base):
    __tablename__ = "class_memberships"
    __table_args__ = (
        UniqueConstraint("classroom_id", "user_id", name="uq_class_membership_class_user"),
        Index("ix_class_memberships_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classroom_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[ClassRole] = mapped_column(enum_type(ClassRole, "class_role"), nullable=False)
    status: Mapped[MembershipStatus] = mapped_column(
        enum_type(MembershipStatus, "class_membership_status"),
        nullable=False,
        default=MembershipStatus.ACTIVE,
    )


class StudentGroup(TimestampMixin, Base):
    __tablename__ = "student_groups"
    __table_args__ = (
        UniqueConstraint("classroom_id", "name", name="uq_student_groups_class_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classroom_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class StudentGroupMembership(TimestampMixin, Base):
    __tablename__ = "student_group_memberships"
    __table_args__ = (
        UniqueConstraint("group_id", "student_id", name="uq_student_group_member"),
        Index("ix_student_group_memberships_student_id", "student_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("student_groups.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


class Invite(TimestampMixin, Base):
    __tablename__ = "invites"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_invites_token_hash"),
        CheckConstraint("max_uses > 0", name="ck_invites_max_uses_positive"),
        CheckConstraint("uses >= 0", name="ck_invites_uses_nonnegative"),
        Index("ix_invites_classroom_id", "classroom_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classroom_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[InviteStatus] = mapped_column(
        enum_type(InviteStatus, "invite_status"), nullable=False, default=InviteStatus.ACTIVE
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TelegramIdentity(TimestampMixin, Base):
    __tablename__ = "telegram_identities"
    __table_args__ = (
        UniqueConstraint("telegram_user_id", name="uq_telegram_identity_telegram_user"),
        UniqueConstraint("user_id", name="uq_telegram_identity_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    telegram_user_id: Mapped[int] = mapped_column(nullable=False)
    telegram_username: Mapped[str | None] = mapped_column(String(64))


class Assignment(TimestampMixin, Base):
    __tablename__ = "assignments"
    __table_args__ = (
        Index("ix_assignments_classroom_status", "classroom_id", "status"),
        Index("ix_assignments_due_at", "due_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classroom_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("classrooms.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[AssignmentTargetType] = mapped_column(
        enum_type(AssignmentTargetType, "assignment_target_type"), nullable=False
    )
    status: Mapped[AssignmentStatus] = mapped_column(
        enum_type(AssignmentStatus, "assignment_status"),
        nullable=False,
        default=AssignmentStatus.DRAFT,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)


class AssignmentRecipient(TimestampMixin, Base):
    __tablename__ = "assignment_recipients"
    __table_args__ = (
        UniqueConstraint("assignment_id", "student_id", name="uq_assignment_recipient_student"),
        Index("ix_assignment_recipients_student_status", "student_id", "status"),
        Index("ix_assignment_recipients_assignment_status", "assignment_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source_group_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("student_groups.id", ondelete="SET NULL")
    )
    status: Mapped[RecipientStatus] = mapped_column(
        enum_type(RecipientStatus, "recipient_status"),
        nullable=False,
        default=RecipientStatus.PENDING,
    )
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Submission(TimestampMixin, Base):
    __tablename__ = "submissions"
    __table_args__ = (
        Index("ix_submissions_recipient_created", "assignment_recipient_id", "created_at"),
        CheckConstraint(
            "(text_content IS NOT NULL AND length(trim(text_content)) > 0) OR file_path IS NOT NULL",
            name="ck_submission_has_text_or_file",
        ),
        CheckConstraint(
            "(file_path IS NULL AND file_name IS NULL AND mime_type IS NULL AND file_size_bytes IS NULL) "
            "OR (file_path IS NOT NULL AND file_name IS NOT NULL AND mime_type IS NOT NULL "
            "AND file_size_bytes IS NOT NULL AND file_size_bytes > 0)",
            name="ck_submission_file_metadata_complete",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_recipient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assignment_recipients.id", ondelete="CASCADE"),
        nullable=False,
    )
    submitted_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    text_content: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(String(500))
    file_name: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(150))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)


class Feedback(TimestampMixin, Base):
    __tablename__ = "feedback"
    __table_args__ = (Index("ix_feedback_submission_id", "submission_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    feedback_text: Mapped[str] = mapped_column(Text, nullable=False)


class Reminder(TimestampMixin, Base):
    __tablename__ = "reminders"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_reminders_idempotency_key"),
        Index("ix_reminders_status_scheduled", "status", "scheduled_at"),
        CheckConstraint("attempt_count >= 0", name="ck_reminders_attempt_count_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_recipient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("assignment_recipients.id", ondelete="CASCADE"),
        nullable=False,
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ReminderStatus] = mapped_column(
        enum_type(ReminderStatus, "reminder_status"),
        nullable=False,
        default=ReminderStatus.PENDING,
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class ActivityEvent(Base):
    __tablename__ = "activity_events"
    __table_args__ = (
        Index("ix_activity_events_school_created", "school_id", "created_at"),
        Index("ix_activity_events_entity", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
