"""Request and response schemas for teacher reviews."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.db.models import RecipientStatus


class ReviewSubmissionRequest(BaseModel):
    feedback_text: str = Field(min_length=1, max_length=5000)
    decision: Literal["completed", "needs_revision"]

    @field_validator("feedback_text")
    @classmethod
    def normalize_feedback(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Feedback cannot be empty.")
        return value


class ReviewSubmissionResponse(BaseModel):
    submission_id: UUID
    feedback_id: UUID
    author_id: UUID
    feedback_text: str
    recipient_id: UUID
    recipient_status: RecipientStatus
    completed_at: datetime | None


class TeacherSubmissionListItem(BaseModel):
    """Submission details safe to return to an authorized classroom teacher."""

    submission_id: UUID
    assignment_id: UUID
    assignment_title: str
    assignment_instructions: str
    due_at: datetime | None
    recipient_id: UUID
    student_id: UUID
    student_name: str
    recipient_status: RecipientStatus
    submitted_at: datetime | None
    submission_created_at: datetime
    text_content: str | None
    file_name: str | None
    mime_type: str | None
    file_size_bytes: int | None
