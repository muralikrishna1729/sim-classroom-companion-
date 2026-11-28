"""Authenticated in-app notification endpoints."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.domains.notifications import (
    count_unread_notifications,
    list_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)
from app.schemas.notification import (
    NotificationListResponse,
    NotificationMarkAllReadResponse,
    NotificationReadResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=NotificationListResponse)
async def get_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> NotificationListResponse:
    items = await list_user_notifications(
        db, user_id=current_user.id, limit=limit, offset=offset
    )
    unread_count = await count_unread_notifications(db, user_id=current_user.id)
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(item) for item in items],
        unread_count=unread_count,
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count", response_model=NotificationUnreadCountResponse)
async def get_unread_notification_count(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationUnreadCountResponse:
    return NotificationUnreadCountResponse(
        unread_count=await count_unread_notifications(db, user_id=current_user.id)
    )


@router.patch("/{notification_id}/read", response_model=NotificationReadResponse)
async def mark_notification_as_read(
    notification_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationReadResponse:
    notification = await mark_notification_read(
        db, notification_id=notification_id, user_id=current_user.id
    )
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    await db.commit()
    await db.refresh(notification)
    return NotificationReadResponse(id=notification.id, read_at=notification.read_at)


@router.patch("/read-all", response_model=NotificationMarkAllReadResponse)
async def mark_all_as_read(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationMarkAllReadResponse:
    updated_count = await mark_all_notifications_read(db, user_id=current_user.id)
    await db.commit()
    return NotificationMarkAllReadResponse(updated_count=updated_count)
