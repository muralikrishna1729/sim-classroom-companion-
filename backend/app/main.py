from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.config import get_settings
from app.db.session import engine
from app.api.auth import router as auth_router
from app.api.schools import router as schools_router
from app.api.classrooms import router as classrooms_router
from app.api.assignments import router as assignments_router
from app.api.submissions import router as submissions_router
from app.api.reviews import router as reviews_router

settings = get_settings()

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Release shared database resources during application shutdown."""
    yield
    await engine.dispose()

app = FastAPI(title=settings.app_name, version="0.1.0", description="Backend API for SIM Classroom Companion.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])

app.include_router(auth_router, prefix="/api/v1")
app.include_router(schools_router, prefix="/api/v1")
app.include_router(classrooms_router, prefix="/api/v1")
app.include_router(assignments_router, prefix="/api/v1")
app.include_router(submissions_router, prefix="/api/v1")
app.include_router(reviews_router, prefix="/api/v1")

@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "running"}

@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/health/ready", tags=["health"])
async def readiness() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ready", "database": "connected"}
