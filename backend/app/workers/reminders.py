"""Background worker for assignment deadline reminders.

Run with: python -m app.workers.reminders
The worker uses database row locks to avoid two processes claiming the same
pending reminder. Telegram delivery is at-least-once if a process crashes
after Telegram accepts a message but before the database records success.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.db.models import (
    Assignment,
    AssignmentRecipient,
    AssignmentStatus,
    Reminder,
    ReminderStatus,
    RecipientStatus,
    TelegramIdentity,
    User,
)
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
RETRY_DELAY = timedelta(minutes=5)
POLL_INTERVAL_SECONDS = 30
PROCESSING_LEASE = timedelta(minutes=2)


class TelegramDeliveryError(RuntimeError):
    """Raised when Telegram rejects a reminder message."""


async def send_telegram_message(
    bot_token: str,
    chat_id: int,
    message: str,
) -> None:
    """Send a plain-text Telegram message and validate the Bot API response."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            json={"chat_id": chat_id, "text": message},
        )
        response.raise_for_status()
        payload = response.json()
    if not payload.get("ok"):
        description = payload.get("description", "Telegram rejected the message")
        raise TelegramDeliveryError(description)


async def _recover_stale_processing_reminders(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
) -> int:
    """Return reminders abandoned by a crashed worker to the pending queue."""
    cutoff = now - PROCESSING_LEASE
    async with session_factory() as session:
        result = await session.scalars(
            select(Reminder).where(
                Reminder.status == ReminderStatus.PROCESSING,
                Reminder.scheduled_at <= cutoff,
            )
        )
        stale = list(result.all())
        for reminder in stale:
            reminder.status = ReminderStatus.PENDING
            reminder.scheduled_at = now
            reminder.last_error = "Recovered after worker processing lease expired."
        if stale:
            await session.commit()
        return len(stale)


async def _claim_due_reminders(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    batch_size: int,
) -> list[UUID]:
    """Atomically move due reminders to PROCESSING and commit the claim."""
    async with session_factory() as session:
        result = await session.scalars(
            select(Reminder)
            .join(
                AssignmentRecipient,
                AssignmentRecipient.id == Reminder.assignment_recipient_id,
            )
            .join(Assignment, Assignment.id == AssignmentRecipient.assignment_id)
            .where(
                Reminder.status == ReminderStatus.PENDING,
                Reminder.scheduled_at <= now,
            )
            .order_by(Reminder.scheduled_at, Reminder.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True, of=Reminder)
        )
        reminders = list(result.all())
        reminder_ids = [reminder.id for reminder in reminders]
        for reminder in reminders:
            reminder.status = ReminderStatus.PROCESSING
            reminder.attempt_count += 1
            # Reuse scheduled_at as the processing-lease timestamp while
            # PROCESSING; the original due time is no longer needed.
            reminder.scheduled_at = now
        await session.commit()
        return reminder_ids


async def _finish_reminder(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    reminder_id: UUID,
    success: bool,
    error: str | None = None,
    now: datetime,
) -> None:
    async with session_factory() as session:
        reminder = await session.get(Reminder, reminder_id)
        if reminder is None or reminder.status != ReminderStatus.PROCESSING:
            return
        if success:
            reminder.status = ReminderStatus.SENT
            reminder.sent_at = now
            reminder.last_error = None
        elif reminder.attempt_count < MAX_ATTEMPTS:
            reminder.status = ReminderStatus.PENDING
            reminder.scheduled_at = now + RETRY_DELAY
            reminder.last_error = (error or "Telegram delivery failed")[:1000]
        else:
            reminder.status = ReminderStatus.FAILED
            reminder.last_error = (error or "Telegram delivery failed")[:1000]
        await session.commit()


async def _load_delivery_details(
    session: AsyncSession,
    reminder_id: UUID,
) -> tuple[Reminder, Assignment, AssignmentRecipient, User, TelegramIdentity] | None:
    result = await session.execute(
        select(Reminder, Assignment, AssignmentRecipient, User, TelegramIdentity)
        .join(
            AssignmentRecipient,
            AssignmentRecipient.id == Reminder.assignment_recipient_id,
        )
        .join(Assignment, Assignment.id == AssignmentRecipient.assignment_id)
        .join(User, User.id == AssignmentRecipient.student_id)
        .outerjoin(TelegramIdentity, TelegramIdentity.user_id == User.id)
        .where(Reminder.id == reminder_id)
    )
    row = result.one_or_none()
    if row is None:
        return None
    reminder, assignment, recipient, user, identity = row
    if identity is None:
        return None
    return reminder, assignment, recipient, user, identity


async def process_due_reminders(
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
    *,
    bot_token: str | None = None,
    now: datetime | None = None,
    batch_size: int = 100,
) -> dict[str, int]:
    """Claim and deliver one batch of due reminders."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    token = bot_token if bot_token is not None else get_settings().telegram_bot_token

    recovered = await _recover_stale_processing_reminders(
        session_factory, now=current_time
    )
    if recovered:
        logger.warning("Recovered %d stale reminder(s) from PROCESSING", recovered)

    reminder_ids = await _claim_due_reminders(
        session_factory,
        now=current_time,
        batch_size=batch_size,
    )
    counts = {
        "claimed": len(reminder_ids), "sent": 0, "retrying": 0,
        "failed": 0, "cancelled": 0, "recovered": recovered,
    }

    for reminder_id in reminder_ids:
        async with session_factory() as session:
            details = await _load_delivery_details(session, reminder_id)
            if details is None:
                reminder = await session.get(Reminder, reminder_id)
                if reminder is not None:
                    reminder.status = ReminderStatus.FAILED
                    reminder.last_error = "Student has no linked Telegram account."
                    await session.commit()
                counts["failed"] += 1
                logger.error("Reminder %s failed: student has no linked Telegram account", reminder_id)
                continue
            reminder, assignment, recipient, user, identity = details
            if (
                assignment.status != AssignmentStatus.ASSIGNED
                or recipient.status in {RecipientStatus.SUBMITTED, RecipientStatus.COMPLETED}
            ):
                reminder.status = ReminderStatus.CANCELLED
                reminder.last_error = None
                await session.commit()
                counts["cancelled"] += 1
                logger.info("Reminder %s cancelled because its assignment is no longer active", reminder_id)
                continue
            assignment_title = assignment.title
            due_at = assignment.due_at
            chat_id = identity.telegram_user_id
            student_name = user.full_name

        if not token:
            error = "Telegram bot token is not configured."
            async with session_factory() as session:
                reminder = await session.get(Reminder, reminder_id)
                if reminder is not None and reminder.status == ReminderStatus.PROCESSING:
                    reminder.status = ReminderStatus.FAILED
                    reminder.last_error = error
                    await session.commit()
            counts["failed"] += 1
            logger.error("Reminder %s failed: Telegram bot token is not configured", reminder_id)
            continue

        due_label = due_at.isoformat() if due_at else "the assigned deadline"
        message = (
            f"Assignment reminder: {assignment_title}\\n"
            f"Hi {student_name}, please remember to submit your assignment.\\n"
            f"Due: {due_label}"
        )
        try:
            await send_telegram_message(token, chat_id, message)
        except (httpx.HTTPError, TelegramDeliveryError, ValueError) as exc:
            await _finish_reminder(
                session_factory, reminder_id=reminder_id, success=False,
                error=str(exc), now=current_time,
            )
            attempt_count = await _attempt_count(session_factory, reminder_id)
            result_key = "retrying" if attempt_count < MAX_ATTEMPTS else "failed"
            counts[result_key] += 1
            logger.warning(
                "Reminder %s Telegram delivery failed (attempt %d/%d): %s",
                reminder_id, attempt_count, MAX_ATTEMPTS, exc,
            )
        else:
            await _finish_reminder(
                session_factory, reminder_id=reminder_id, success=True,
                now=current_time,
            )
            counts["sent"] += 1
            logger.info("Reminder %s sent successfully to Telegram chat %s", reminder_id, chat_id)

    return counts


async def _attempt_count(
    session_factory: async_sessionmaker[AsyncSession],
    reminder_id: UUID,
) -> int:
    async with session_factory() as session:
        reminder = await session.get(Reminder, reminder_id)
        return reminder.attempt_count if reminder is not None else MAX_ATTEMPTS


async def run_worker() -> None:
    """Verify configuration/database, then poll continuously."""
    settings = get_settings()
    logger.info("Starting SIM Classroom Companion Telegram reminder worker")
    logger.info("Polling interval: %d seconds", POLL_INTERVAL_SECONDS)
    logger.info("Telegram bot token configured: %s", "yes" if settings.telegram_bot_token else "no")
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN is not configured; due reminders will be marked failed")

    # Fail fast if the database is unavailable instead of silently polling.
    async with AsyncSessionLocal() as session:
        await session.execute(select(1))
    logger.info("Database connectivity check passed; worker is ready")

    try:
        while True:
            started_at = datetime.now(timezone.utc)
            try:
                counts = await process_due_reminders(bot_token=settings.telegram_bot_token)
                logger.info("Reminder poll completed in %.2fs: %s", (datetime.now(timezone.utc) - started_at).total_seconds(), counts)
            except Exception:
                logger.exception("Reminder worker iteration failed")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        logger.info("Telegram reminder worker stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, get_settings().log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Telegram reminder worker interrupted by user")
