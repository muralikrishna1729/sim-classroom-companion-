"""Seed a repeatable, local-only classroom demo dataset.

Run from backend/: python -m scripts.seed_demo
This script is additive and idempotent; it never deletes existing records.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import (
    Assignment,
    ClassMembership,
    ClassRole,
    Classroom,
    MembershipStatus,
    School,
    SchoolMembership,
    SchoolRole,
    User,
)
from app.db.session import AsyncSessionLocal
from app.domains.assignments import create_assignment
from app.db.models import AssignmentTargetType


DEMO_PASSWORD = "ClassroomDemo!2026"
SCHOOL_NAME = "SIM Demo Academy"
TIMEZONE = "Asia/Kolkata"

USERS = [
    {"full_name": "Demo Coordinator", "email": "coordinator@sim-demo.test", "role": "coordinator"},
    {"full_name": "Aarav Sharma", "email": "teacher1@sim-demo.test", "role": "teacher"},
    {"full_name": "Diya Reddy", "email": "teacher2@sim-demo.test", "role": "teacher"},
]

CLASSROOMS = [
    {"name": "Class 8-A", "grade": "Grade 8", "teacher": "teacher1@sim-demo.test",
     "students": [("Aanya Patel", "student01@sim-demo.test"), ("Vivaan Rao", "student02@sim-demo.test"),
                  ("Ishita Kumar", "student03@sim-demo.test"), ("Arjun Mehta", "student04@sim-demo.test")]},
    {"name": "Class 9-A", "grade": "Grade 9", "teacher": "teacher1@sim-demo.test",
     "students": [("Saanvi Nair", "student05@sim-demo.test"), ("Aditya Shah", "student06@sim-demo.test"),
                  ("Anaya Das", "student07@sim-demo.test")]},
    {"name": "Class 10-A", "grade": "Grade 10", "teacher": "teacher2@sim-demo.test",
     "students": [("Reyansh Iyer", "student08@sim-demo.test"), ("Myra Singh", "student09@sim-demo.test"),
                  ("Kabir Joshi", "student10@sim-demo.test")]},
]


async def get_or_create_user(session, full_name: str, email: str) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            full_name=full_name,
            email=email,
            password_hash=hash_password(DEMO_PASSWORD),
            is_active=True,
        )
        session.add(user)
        await session.flush()
    else:
        # Reset only these explicitly reserved demo accounts to the documented
        # local demo password. No non-demo users are modified.
        user.full_name = full_name
        user.password_hash = hash_password(DEMO_PASSWORD)
        user.is_active = True
    return user


async def ensure_class_membership(session, classroom_id, user_id, role: ClassRole) -> None:
    membership = await session.scalar(
        select(ClassMembership).where(
            ClassMembership.classroom_id == classroom_id,
            ClassMembership.user_id == user_id,
        )
    )
    if membership is None:
        session.add(ClassMembership(
            classroom_id=classroom_id,
            user_id=user_id,
            role=role,
            status=MembershipStatus.ACTIVE,
        ))
    elif membership.role != role:
        raise RuntimeError(
            f"Role conflict for user {user_id} in classroom {classroom_id}; "
            "refusing to overwrite an existing membership."
        )
    else:
        membership.status = MembershipStatus.ACTIVE


async def seed() -> None:
    settings = get_settings()
    if settings.app_env.lower() not in {"development", "dev", "local"}:
        raise RuntimeError(
            "Demo seeding is disabled unless APP_ENV is development, dev, or local."
        )

    async with AsyncSessionLocal() as session:
        async with session.begin():
            school = await session.scalar(select(School).where(School.name == SCHOOL_NAME))
            if school is None:
                school = School(name=SCHOOL_NAME, timezone=TIMEZONE, is_active=True)
                session.add(school)
                await session.flush()
            else:
                school.timezone = TIMEZONE
                school.is_active = True

            users_by_email = {}
            for item in USERS:
                users_by_email[item["email"]] = await get_or_create_user(
                    session, item["full_name"], item["email"]
                )

            for index in range(1, 11):
                name = next(
                    student_name
                    for classroom in CLASSROOMS
                    for student_name, email in classroom["students"]
                    if email == f"student{index:02d}@sim-demo.test"
                )
                email = f"student{index:02d}@sim-demo.test"
                users_by_email[email] = await get_or_create_user(session, name, email)

            coordinator = users_by_email["coordinator@sim-demo.test"]
            school_membership = await session.scalar(
                select(SchoolMembership).where(
                    SchoolMembership.school_id == school.id,
                    SchoolMembership.user_id == coordinator.id,
                )
            )
            if school_membership is None:
                session.add(SchoolMembership(
                    school_id=school.id,
                    user_id=coordinator.id,
                    role=SchoolRole.COORDINATOR,
                    status=MembershipStatus.ACTIVE,
                ))
            else:
                school_membership.status = MembershipStatus.ACTIVE

            for spec in CLASSROOMS:
                classroom = await session.scalar(
                    select(Classroom).where(
                        Classroom.school_id == school.id,
                        Classroom.name == spec["name"],
                    )
                )
                if classroom is None:
                    classroom = Classroom(
                        school_id=school.id,
                        name=spec["name"],
                        grade_label=spec["grade"],
                    )
                    session.add(classroom)
                    await session.flush()

                teacher = users_by_email[spec["teacher"]]
                await ensure_class_membership(
                    session, classroom.id, teacher.id, ClassRole.TEACHER
                )

                for _student_name, student_email in spec["students"]:
                    student = users_by_email[student_email]
                    await ensure_class_membership(
                        session, classroom.id, student.id, ClassRole.STUDENT
                    )

                title = f"{spec['name']} - Welcome assignment"
                existing_assignment = await session.scalar(
                    select(Assignment).where(
                        Assignment.classroom_id == classroom.id,
                        Assignment.title == title,
                    )
                )
                if existing_assignment is None:
                    await create_assignment(
                        session,
                        actor_user_id=teacher.id,
                        classroom_id=classroom.id,
                        title=title,
                        instructions=(
                            "Welcome to SIM Classroom Companion. Submit a short "
                            "introduction and describe one learning goal for this term."
                        ),
                        target_type=AssignmentTargetType.CLASS,
                        timezone_name=school.timezone,
                        due_at=datetime.now(ZoneInfo(TIMEZONE)) + timedelta(days=7),
                    )

        print("\nDemo data is ready.")
        print(f"School: {SCHOOL_NAME} ({TIMEZONE})")
        print("Classrooms: Class 8-A, Class 9-A, Class 10-A")
        print("Accounts: 1 coordinator, 2 teachers, 10 students")
        print(f"Password for every demo account: {DEMO_PASSWORD}")
        print("Use the email list in DEMO_ACCOUNTS.md to sign in.")


if __name__ == "__main__":
    asyncio.run(seed())
