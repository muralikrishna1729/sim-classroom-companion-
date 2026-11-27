# Implementation Plan

## Phase 1 — Backend foundation
- [x] Repository structure and baseline configuration
- [x] FastAPI application and health endpoints
- [x] Async SQLAlchemy engine/session
- [x] Docker Compose PostgreSQL and API services
- [x] Alembic environment
- [ ] Validate container build and local startup
- [ ] Add first domain models and initial migration

## Phase 2 — Identity and school structure
- [ ] School, user, classroom and membership models
- [ ] Email/password authentication and secure sessions
- [ ] School/classroom-scoped authorization
- [ ] Invitation creation, expiry and student linking

## Phase 3 — Assignment workflow
- [ ] Assignment creation and editing
- [ ] Per-student assignment recipients
- [ ] Validated progress state transitions
- [ ] Submission and teacher feedback

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
