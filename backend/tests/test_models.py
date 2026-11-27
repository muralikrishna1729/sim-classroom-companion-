from app.db.base import Base
from app.db import models  # noqa: F401 — import registers mapped tables


def test_core_domain_tables_are_registered() -> None:
    expected = {
        "schools",
        "users",
        "school_memberships",
        "classrooms",
        "class_memberships",
        "student_groups",
        "student_group_memberships",
        "invites",
        "telegram_identities",
        "assignments",
        "assignment_recipients",
        "submissions",
        "feedback",
        "reminders",
        "activity_events",
    }
    assert expected.issubset(Base.metadata.tables.keys())


def test_assignment_recipient_is_unique_per_student_and_assignment() -> None:
    table = Base.metadata.tables["assignment_recipients"]
    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("assignment_id", "student_id") in unique_column_sets


def test_telegram_identity_is_unique_per_user_and_telegram_account() -> None:
    table = Base.metadata.tables["telegram_identities"]
    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("telegram_user_id",) in unique_column_sets
    assert ("user_id",) in unique_column_sets


def test_submission_requires_text_or_complete_file_metadata() -> None:
    table = Base.metadata.tables["submissions"]
    check_names = {
        constraint.name
        for constraint in table.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }
    assert "ck_submission_has_text_or_file" in check_names
    assert "ck_submission_file_metadata_complete" in check_names
