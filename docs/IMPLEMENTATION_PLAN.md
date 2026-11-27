# Implementation Plan

## Phase 1 — Backend foundation
- [x] Repository structure and baseline configuration
- [x] FastAPI application and health endpoints
- [x] Async SQLAlchemy engine/session
- [x] Docker Compose PostgreSQL and API services
- [x] Alembic environment
- [x] Initial relational ORM models and metadata tests
- [ ] Validate container build and local startup
- [ ] Generate and review the initial Alembic migration
- [ ] Apply migration against local PostgreSQL

## Phase 2 — Identity and school structure
- [ ] Email/password authentication and secure sessions
- [ ] School/classroom-scoped authorization
- [ ] Invitation creation, expiry and student linking
- [x] Domain rule for teacher-authorized student group membership
- [ ] Enforce school and classroom consistency with database-level constraints where practical

## Phase 3 — Assignment workflow
- [x] Assignment targeting for class, individual and group recipients
- [x] Per-student recipient creation and duplicate protection
- [x] Student progress transition rules
- [x] Student-authorized text/file-reference submission service
- [ ] Teacher feedback and review service
- [ ] API routes and integration tests for assignment workflows

## Phase 4 — Integrations and reminders
- [ ] Telegram bot adapter and idempotent update handling
- [ ] Telegram identity linking
- [ ] Groq structured interpretation adapter
- [ ] Persisted reminder records and retry-safe scheduler

## Phase 5 — React and demonstration
- [ ] Teacher and student views
- [ ] Connect frontend to API
- [ ] End-to-end tests for required scenarios
- [ ] README demo guide and architecture walkthrough

## Verification note

GitHub commits confirm that source files were created. A GitHub Actions test workflow has been added, but its run result has not yet been inspected. Python tests, Alembic generation, database migration, and Docker startup must be verified before calling the backend runnable.
