from app.db.models import RecipientStatus
from app.domains.assignments import (
    ALLOWED_RECIPIENT_TRANSITIONS,
    DomainRuleViolation,
)


def test_pending_can_be_acknowledged_or_started() -> None:
    assert ALLOWED_RECIPIENT_TRANSITIONS[RecipientStatus.PENDING] == {
        RecipientStatus.ACKNOWLEDGED,
        RecipientStatus.IN_PROGRESS,
    }


def test_in_progress_can_be_blocked_but_submission_uses_dedicated_service() -> None:
    assert ALLOWED_RECIPIENT_TRANSITIONS[RecipientStatus.IN_PROGRESS] == {
        RecipientStatus.BLOCKED,
    }


def test_blocked_can_only_resume_through_progress_service() -> None:
    assert ALLOWED_RECIPIENT_TRANSITIONS[RecipientStatus.BLOCKED] == {
        RecipientStatus.IN_PROGRESS,
    }


def test_needs_revision_can_resume_work() -> None:
    assert ALLOWED_RECIPIENT_TRANSITIONS[RecipientStatus.NEEDS_REVISION] == {
        RecipientStatus.IN_PROGRESS,
    }


def test_submitted_and_completed_are_not_student_progress_updates() -> None:
    assert ALLOWED_RECIPIENT_TRANSITIONS[RecipientStatus.SUBMITTED] == set()
    assert ALLOWED_RECIPIENT_TRANSITIONS[RecipientStatus.COMPLETED] == set()


def test_every_recipient_state_has_a_transition_definition() -> None:
    assert set(ALLOWED_RECIPIENT_TRANSITIONS) == set(RecipientStatus)


def test_domain_rule_violation_is_a_value_error() -> None:
    error = DomainRuleViolation("invalid operation")
    assert isinstance(error, ValueError)
    assert str(error) == "invalid operation"
