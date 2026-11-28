"""Authentication API endpoints: registration, login, and current user."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import create_access_token, verify_password
from app.db.models import User
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.domains.registration import RegistrationRuleViolation, register_user
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.schemas.registration import RegistrationRequest, RegistrationResponse, RegisteredUserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegistrationRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> RegistrationResponse:
    try:
        user = await register_user(db, full_name=request.full_name, email=request.email, password=request.password)
        await db.commit()
        await db.refresh(user)
    except RegistrationRuleViolation as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.") from None
    token = create_access_token(subject=user.id)
    return RegistrationResponse(user=RegisteredUserResponse.model_validate(user), access_token=token)

@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> TokenResponse:
    result = await db.execute(select(User).where(func.lower(User.email) == credentials.email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.", headers={"WWW-Authenticate": "Bearer"})
    return TokenResponse(access_token=create_access_token(subject=user.id))

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    return UserResponse.model_validate(current_user)
