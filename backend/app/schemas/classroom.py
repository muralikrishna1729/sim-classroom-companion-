"""Request and response schemas for classroom operations."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClassroomCreateRequest(BaseModel):
    school_id: UUID
    name: str = Field(min_length=2, max_length=120)
    grade_label: str | None = Field(default=None, max_length=80)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Classroom name must contain at least 2 characters.")
        return value

    @field_validator("grade_label")
    @classmethod
    def normalize_grade(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ClassroomMemberRequest(BaseModel):
    user_id: UUID


class ClassroomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    school_id: UUID
    name: str
    grade_label: str | None


class ClassroomMembershipResponse(BaseModel):
    classroom_id: UUID
    user_id: UUID
    role: str
    status: str
