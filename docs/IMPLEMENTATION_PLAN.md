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
- [ ] Enforce school and classroom consistency across memberships and group membership

## Phase 3 — Assignment workflow
- [ ] Assignment creation and editing
- [ ] Resolve class, individual and group targets into recipient records
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

## Verification note

GitHub file creation confirms that the source files were committed. Python tests, Alembic generation, database migration, and Docker startup have not yet been executed in a local runtime and must be verified when a development machine is available.
