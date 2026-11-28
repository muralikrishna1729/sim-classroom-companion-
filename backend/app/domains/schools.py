"""School creation and school-level access rules."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import MembershipStatus, School, SchoolMembership, SchoolRole

async def create_school(db: AsyncSession, *, actor_user_id, name: str, timezone: str) -> School:
    school = School(name=name, timezone=timezone, is_active=True)
    db.add(school)
    await db.flush()
    db.add(SchoolMembership(school_id=school.id, user_id=actor_user_id, role=SchoolRole.COORDINATOR, status=MembershipStatus.ACTIVE))
    await db.flush()
    return school

async def list_user_schools(db: AsyncSession, *, user_id):
    result = await db.execute(
        select(School).join(SchoolMembership, SchoolMembership.school_id == School.id)
        .where(SchoolMembership.user_id == user_id, SchoolMembership.status == MembershipStatus.ACTIVE, School.is_active.is_(True))
    )
    return list(result.scalars().all())
