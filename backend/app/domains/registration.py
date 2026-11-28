"""Registration use cases and business rules."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import hash_password
from app.db.models import User

class RegistrationRuleViolation(Exception):
    """Raised when registration violates a business rule."""

async def register_user(db: AsyncSession, *, full_name: str, email: str, password: str) -> User:
    result = await db.execute(select(User.id).where(func.lower(User.email) == email.lower()))
    if result.scalar_one_or_none() is not None:
        raise RegistrationRuleViolation("An account with this email already exists.")
    user = User(full_name=full_name, email=email.lower(), password_hash=hash_password(password), is_active=True)
    db.add(user)
    await db.flush()
    return user
