"""In-app notification business rules. The caller owns the transaction."""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Notification


async def create_notification(
    session: AsyncSession,
    *,
    user_id: UUID,
    notification_type: str,
    title: str,
    message: str,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    payload: dict | None = None,
) -> Notification:
    """Create one in-app notification; delivery is handled by a separate worker."""
    notification = Notification(
        user_id=user_id,
        notification_type=notification_type.strip(),
        title=title.strip(),
        message=message.strip(),
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
    )
    session.add(notification)
    await session.flush()
    return notification


async def list_user_notifications(
    session: AsyncSession, *, user_id: UUID, limit: int = 30, offset: int = 0
) -> list[Notification]:
    result = await session.scalars(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.all())


async def count_unread_notifications(session: AsyncSession, *, user_id: UUID) -> int:
    count = await session.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id, Notification.read_at.is_(None)
        )
    )
    return int(count or 0)


async def mark_notification_read(
    session: AsyncSession, *, notification_id: UUID, user_id: UUID
) -> Notification | None:
    notification = await session.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
    )
    if notification is None:
        return None
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        await session.flush()
    return notification


async def mark_all_notifications_read(session: AsyncSession, *, user_id: UUID) -> int:
    result = await session.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(timezone.utc))
    )
    await session.flush()
    return int(result.rowcount or 0)
