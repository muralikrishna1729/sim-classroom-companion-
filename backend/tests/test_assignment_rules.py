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


def test_blocked_can_resume_or_be_submitted() -> None:
    assert ALLOWED_RECIPIENT_TRANSITIONS[RecipientStatus.BLOCKED] == {
        RecipientStatus.IN_PROGRESS,
        RecipientStatus.SUBMITTED,
    }


def test_completed_is_terminal() -> None:
    assert ALLOWED_RECIPIENT_TRANSITIONS[RecipientStatus.COMPLETED] == set()


def test_every_recipient_state_has_a_transition_definition() -> None:
    assert set(ALLOWED_RECIPIENT_TRANSITIONS) == set(RecipientStatus)


def test_domain_rule_violation_is_a_value_error() -> None:
    error = DomainRuleViolation("invalid operation")
    assert isinstance(error, ValueError)
    assert str(error) == "invalid operation"
