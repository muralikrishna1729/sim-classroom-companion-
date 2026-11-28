"""Request and response schemas for assignment operations."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import AssignmentTargetType, RecipientStatus


class AssignmentCreateRequest(BaseModel):
    classroom_id: UUID
    title: str = Field(min_length=2, max_length=200)
    instructions: str = Field(min_length=1, max_length=20000)
    target_type: AssignmentTargetType
    timezone: str = Field(min_length=1, max_length=64)
    due_at: datetime | None = None
    student_ids: list[UUID] | None = None
    group_ids: list[UUID] | None = None

    @field_validator("title", "instructions", "timezone")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value

    @field_validator("title")
    @classmethod
    def require_two_character_title(cls, value: str) -> str:
        if len(value) < 2:
            raise ValueError("Title must contain at least 2 non-whitespace characters.")
        return value


class AssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    classroom_id: UUID
    created_by_id: UUID
    title: str
    instructions: str
    target_type: AssignmentTargetType
    status: str
    due_at: datetime | None
    timezone: str
    recipient_ids: list[UUID]


class RecipientProgressRequest(BaseModel):
    status: RecipientStatus
    blocked_reason: str | None = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def restrict_student_progress_status(cls, value: RecipientStatus) -> RecipientStatus:
        allowed = {
            RecipientStatus.ACKNOWLEDGED,
            RecipientStatus.IN_PROGRESS,
            RecipientStatus.BLOCKED,
        }
        if value not in allowed:
            raise ValueError(
                "Students may only set progress to acknowledged, in_progress, or blocked."
            )
        return value

    @field_validator("blocked_reason")
    @classmethod
    def normalize_blocked_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class RecipientProgressResponse(BaseModel):
    id: UUID
    assignment_id: UUID
    student_id: UUID
    status: RecipientStatus
    blocked_reason: str | None


class AssignmentListItem(BaseModel):
    """Assignment details plus progress belonging only to the requesting student."""

    id: UUID
    classroom_id: UUID
    created_by_id: UUID
    title: str
    instructions: str
    target_type: AssignmentTargetType
    status: str
    due_at: datetime | None
    timezone: str
    recipient_id: UUID | None = None
    my_status: RecipientStatus | None = None
    my_blocked_reason: str | None = None

class SubmissionResponse(BaseModel):
    id: UUID
    assignment_recipient_id: UUID
    text_content: str | None
    file_name: str | None
    mime_type: str | None
    file_size_bytes: int | None

class TeacherAssignmentRecipientProgress(BaseModel):
    recipient_id: UUID
    student_id: UUID
    student_name: str
    status: RecipientStatus
    blocked_reason: str | None
    acknowledged_at: datetime | None
    submitted_at: datetime | None
    completed_at: datetime | None


class TeacherAssignmentProgressResponse(BaseModel):
    assignment_id: UUID
    assignment_status: str
    total_recipients: int
    status_counts: dict[str, int]
    recipients: list[TeacherAssignmentRecipientProgress]


class AssignmentCancellationResponse(BaseModel):
    assignment_id: UUID
    status: str
