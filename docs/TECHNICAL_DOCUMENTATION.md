# SIM Classroom Companion — Technical Documentation

> **Repository:** `muralikrishna1729/sim-classroom-companion`  
> **Branch:** `feature/frontend-demo`  
> **Source revision documented:** `c9e346b3128f2340dae5cf565d628f6200f69057`  
> **Purpose:** Developer onboarding, debugging, extension, and interview preparation.

## Table of contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Repository map](#3-repository-map)
4. [End-to-end workflows](#4-end-to-end-workflows)
5. [Features and implementation](#5-features-and-implementation)
6. [Technical decisions](#6-technical-decisions)
7. [Constraints and limitations](#7-constraints-and-limitations)
8. [Setup, run, and test](#8-setup-run-and-test)
9. [Concept glossary](#9-concept-glossary)
10. [Remaining work](#10-remaining-work)
11. [Open questions](#11-open-questions)

---

## 1. Overview

SIM Classroom Companion is a classroom coordination application for school coordinators, teachers, and students. It organizes schools and classrooms, distributes assignments, tracks each student's progress, accepts submissions, records teacher feedback, and creates in-app notifications. A separate worker can send due-date reminders through Telegram.

### Current implementation status

**Backend code present:** registration/login, JWT authentication, school and classroom membership, assignment targeting (class/individual/group), per-student recipients, progress transitions, submission persistence, teacher review, student feedback/history, notifications, reminder worker, and demo seeding.

**Frontend code present:** login/register, current-user loading, teacher/student workspace presentation switch, classroom and assignment lists, class-wide assignment creation, school setup, and notification display.

**Frontend gaps:** submission upload, teacher review table/actions, student feedback/history screens, and progress controls are placeholders or not fully wired. The role switch changes presentation only; it does not grant backend permissions.

**Not confirmed as implemented:** complete Telegram account linking, Groq-powered natural-language workflows, production deployment, and end-to-end tests on the exact source revision.

## 2. Architecture

### Architecture mind map

```mermaid
mindmap
  root((SIM Classroom Companion))
    React web app
      Auth screens
      Teacher workspace
      Student workspace
      API client
    FastAPI backend
      API routers
      Auth dependencies
      Pydantic schemas
      Domain services
      Local file storage
      Reminder worker
    PostgreSQL
      Users and memberships
      Schools and classrooms
      Assignments and recipients
      Submissions and feedback
      Notifications and reminders
    External service
      Telegram Bot API
    Planned / unconfirmed
      Groq adapter
      Telegram linking flow
```

### Component diagram

```mermaid
flowchart LR
  UI[React + TypeScript + Vite] -->|HTTP + Bearer token| API[FastAPI /api/v1]
  API --> AUTH[JWT auth dependency]
  API --> DOMAIN[Domain services]
  DOMAIN --> DB[(PostgreSQL)]
  API --> STORAGE[Local file storage]
  WORKER[Reminder worker] --> DB
  WORKER --> TG[Telegram Bot API]
```

The browser calls FastAPI. Routes validate HTTP input and authenticate the caller, then delegate business rules to domain services. SQLAlchemy persists state in PostgreSQL. Submission files are stored through the local storage module. The reminder worker is a separate process and is not automatically started by FastAPI.

### Database relationship overview

```mermaid
erDiagram
  SCHOOL ||--o{ CLASSROOM : contains
  SCHOOL ||--o{ SCHOOL_MEMBERSHIP : has
  USER ||--o{ SCHOOL_MEMBERSHIP : joins
  CLASSROOM ||--o{ CLASS_MEMBERSHIP : has
  USER ||--o{ CLASS_MEMBERSHIP : joins
  CLASSROOM ||--o{ ASSIGNMENT : receives
  ASSIGNMENT ||--o{ ASSIGNMENT_RECIPIENT : distributes
  USER ||--o{ ASSIGNMENT_RECIPIENT : assigned_student
  ASSIGNMENT_RECIPIENT ||--o{ SUBMISSION : has_attempts
  SUBMISSION ||--o{ FEEDBACK : receives
  ASSIGNMENT_RECIPIENT ||--o{ REMINDER : schedules
  USER ||--o{ NOTIFICATION : receives
  USER ||--o| TELEGRAM_IDENTITY : links
```

Core ORM entities are defined in `backend/app/db/models.py`: `User`, `School`, `SchoolMembership`, `Classroom`, `ClassMembership`, `StudentGroup`, `StudentGroupMembership`, `Invite`, `TelegramIdentity`, `Assignment`, `AssignmentRecipient`, `Submission`, `Feedback`, `Reminder`, `ActivityEvent`, and `Notification`.

**Important data model:** `Assignment` stores shared task details. `AssignmentRecipient` stores each student's independent status and progress. This avoids one student's progress overwriting another's.

## 3. Repository map

### Root
| Path | Responsibility |
|---|---|
| `README.md` | Project introduction and basic setup; some status notes may be stale. |
| `docker-compose.yml` | PostgreSQL and optional API containers. |
| `.github/workflows/backend-checks.yml` | Backend CI workflow. |
| `docs/ARCHITECTURE.md` | Earlier architecture overview. |
| `docs/DECISIONS.md` | Architecture decision records. |
| `docs/DOMAIN_RULES.md` | Domain invariants and business rules. |
| `docs/IMPLEMENTATION_PLAN.md` | Phase plan; reconcile status with current code. |

### Backend application
| Path | Responsibility |
|---|---|
| `backend/app/main.py` | FastAPI app, lifespan, CORS, router mounting, health routes. |
| `backend/app/core/config.py` | Environment settings. |
| `backend/app/core/security.py` | Password hashing and JWT helpers. |
| `backend/app/db/base.py` | SQLAlchemy declarative base. |
| `backend/app/db/models.py` | ORM models, enums, constraints, indexes. |
| `backend/app/db/session.py` | Async engine, session factory, request DB dependency. |
| `backend/app/dependencies/auth.py` | Resolves current user from bearer token. |

### API routers
| Path | Responsibility |
|---|---|
| `backend/app/api/auth.py` | Register, login, current user. |
| `backend/app/api/schools.py` | School operations. |
| `backend/app/api/classrooms.py` | Classrooms, memberships, groups. |
| `backend/app/api/assignments.py` | Create/list assignments, progress, summaries, cancellation. |
| `backend/app/api/submissions.py` | Student submission, feedback, history routes. |
| `backend/app/api/reviews.py` | Teacher submission listing and review. |
| `backend/app/api/notifications.py` | List/count/read notifications. |

### Domain services, storage, workers
| Path | Responsibility |
|---|---|
| `backend/app/domains/registration.py` | Registration rules. |
| `backend/app/domains/schools.py` | School/coordinator rules. |
| `backend/app/domains/classrooms.py` | Classroom membership, groups, visibility. |
| `backend/app/domains/assignments.py` | Target resolution, recipients, progress, reminders, cancellation. |
| `backend/app/domains/submissions.py` | Submission persistence, feedback/history operations. |
| `backend/app/domains/reviews.py` | Teacher review and submission listing. |
| `backend/app/domains/notifications.py` | Notification operations. |
| `backend/app/storage/local.py` | Local upload validation and persistence. |
| `backend/app/workers/reminders.py` | Due reminder claiming, Telegram send, retries, stale recovery. |
| `backend/scripts/seed_demo.py` | Development-only demo seed. |
| `backend/DEMO_ACCOUNTS.md` | Demo account credentials. |

### Schemas, migrations, tests
- `backend/app/schemas/auth.py`, `registration.py`, `school.py`, `classroom.py`, `assignment.py`, `review.py`, and `notification.py`: API request/response contracts.
- `backend/alembic.ini`, `backend/alembic/env.py`, and `backend/alembic/versions/`: migration configuration and schema history.
- `backend/tests/`: tests for health, models, security, auth, school/classroom, assignments, submissions/storage, reviews, feedback, notifications, and reminder worker.

### Frontend
| Path | Responsibility |
|---|---|
| `frontend/src/main.tsx` | React entry point. |
| `frontend/src/App.tsx` | Main app state, authentication UI, navigation, dashboards, setup, assignment form. |
| `frontend/src/api.ts` | Axios client, token handling, endpoint wrappers, TS types. |
| `frontend/src/styles.css` | Layout and responsive styling. |
| `frontend/src/vite-env.d.ts` | Vite environment type declarations. |
| `frontend/package.json` | Scripts and dependencies. |
| `frontend/vite.config.ts` | Vite configuration. |
| `frontend/tsconfig.json` | TypeScript configuration. |
| `frontend/index.html` | HTML entry page. |
| `frontend/.env.example` | Frontend API URL template. |

Other backend configuration: `backend/requirements.txt`, `backend/Dockerfile`, and `backend/.env.example`.

## 4. End-to-end workflows

### Workflow mind map

```mermaid
mindmap
  root((User journey))
    Authenticate
      Login
      JWT token
      Load profile
    Teacher
      Select classroom
      Create assignment
      Resolve recipients
      Notify students
    Student
      View assignment
      Update progress
      Submit work
    Teacher review
      Inspect attempts
      Record feedback
      Complete or request revision
    Worker
      Claim due reminders
      Send Telegram
      Retry or fail
```

### Assignment creation

```mermaid
flowchart TD
  A[Teacher submits form] --> B[POST /api/v1/assignments]
  B --> C[Authenticate actor]
  C --> D[Load classroom and school]
  D --> E{School active and timezone matches?}
  E -- No --> X[Reject]
  E -- Yes --> F{Active teacher membership?}
  F -- No --> X
  F -- Yes --> G{Target type}
  G --> H[Class: active students]
  G --> I[Individual: selected students]
  G --> J[Group: group members]
  H --> K[Create assignment]
  I --> K
  J --> K
  K --> L[Create one recipient per student]
  L --> M[Create reminders when due date exists]
  M --> N[Create in-app notifications]
  N --> O[Route commits transaction]
```

### Submission and review

```mermaid
sequenceDiagram
  participant S as Student
  participant API as FastAPI
  participant FS as Local storage
  participant DB as PostgreSQL
  participant T as Teacher
  S->>API: Submit text/file
  API->>FS: Validate and save file if supplied
  API->>DB: Lock recipient; check ownership
  API->>DB: Insert submission; set submitted
  API->>DB: Commit
  API-->>S: Submission response
  T->>API: List classroom submissions
  API->>DB: Verify teacher membership
  API-->>T: Submission list
  T->>API: Submit review and feedback
  API->>DB: Insert feedback; update recipient status
  API->>DB: Commit
```

A failed submission transaction rolls back database changes and removes a newly saved file to avoid an orphaned upload.

## 5. Features and implementation

### 5.1 Authentication

**What it does:** Registers users, verifies passwords, issues JWT access tokens, and resolves the current user on protected routes.

**Logic:** registration stores a password hash; login verifies it; token claims include user UUID in `sub`, issue time, expiry, and token type; `get_current_user` validates the bearer token and loads the user. The frontend stores the token and attaches it to requests.

**Key files:** `api/auth.py`, `domains/registration.py`, `core/security.py`, `dependencies/auth.py`, `frontend/src/api.ts`.

Example:
```python
payload = {
    "sub": subject_value,
    "iat": now,
    "exp": now + lifetime,
    "token_type": "access",
}
return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)
```
- `sub`: identity of the user.
- `iat`: token issue time.
- `exp`: expiry.
- `token_type`: intended token type.
- Signing lets the backend detect token tampering.

**Limitations:** frontend uses localStorage; this is convenient for a demo but XSS can expose tokens. Password reset/email verification are not confirmed complete. JWT secret must be configured.

### 5.2 School and classroom membership

**What it does:** Separates school-level coordinator membership from classroom-level teacher/student membership.

**Logic:** school creator becomes coordinator; coordinator creates classrooms and connects registered users; domain services check actor permission, target user state, and membership status. Classroom listing merges coordinator and classroom-member visibility and deduplicates classrooms.

**Key files:** `api/schools.py`, `api/classrooms.py`, `domains/schools.py`, `domains/classrooms.py`, `db/models.py`.

`SchoolMembership` uses school roles such as `coordinator`; `ClassMembership` uses class roles such as `teacher` and `student`. Membership status values include `active`, `invited`, and `inactive`.

**Limitations:** current setup UI adds a student by user UUID and expects prior registration. Email lookup/invitation UX is not exposed. UI role switching does not change backend authorization.

### 5.3 Assignment targeting and distribution

**What it does:** Creates class-wide, individual, or group assignments.

**Logic in `create_assignment`:**
1. Validate title, instructions, timezone name, and timezone-aware deadline.
2. Load classroom and school; require active school.
3. Require assignment timezone to match school timezone.
4. Require active teacher membership.
5. Resolve student IDs for the target type.
6. Reject empty targets and invalid members.
7. Create assignment and one recipient per distinct student.
8. If a deadline exists, create reminders.
9. Create in-app notifications.
10. Flush; the route owns commit/rollback.

Example class target logic:
```python
if target_type == AssignmentTargetType.CLASS:
    if student_ids or group_ids:
        raise DomainRuleViolation(
            "Class targeting cannot include student or group IDs."
        )
    result = await session.execute(
        select(ClassMembership.user_id).where(
            ClassMembership.classroom_id == classroom_id,
            ClassMembership.role == ClassRole.STUDENT,
            ClassMembership.status == MembershipStatus.ACTIVE,
        )
    )
    resolved_student_ids = set(result.scalars().all())
```
Only active students in the selected classroom are included. The set removes duplicates. A unique database constraint on assignment/student is a second line of defense.

**Timezone:** school timezone is authoritative; aware deadlines are converted to UTC for storage. The frontend assignment form was changed to derive timezone from the selected classroom's school rather than browser timezone.

**Limitations:** frontend currently demonstrates class-wide assignment creation; do not assume all target types are exposed in the UI.

### 5.4 Student progress state machine

Allowed transitions include pending → acknowledged/in_progress; acknowledged → in_progress; in_progress ↔ blocked (via the defined transitions); needs_revision → in_progress; submitted → completed/needs_revision through teacher review. Completed is terminal.

```mermaid
stateDiagram-v2
  [*] --> pending
  pending --> acknowledged
  pending --> in_progress
  acknowledged --> in_progress
  in_progress --> blocked
  blocked --> in_progress
  in_progress --> submitted: submission service
  submitted --> completed: teacher review
  submitted --> needs_revision: teacher review
  needs_revision --> in_progress
```

`transition_recipient_status` locks the recipient row, checks student ownership, rejects direct student transitions to submitted/review-only states, validates blocked reason, and checks the transition map.

A row lock serializes concurrent changes to the same recipient while the transaction is active. Blocked status requires a reason; a reason is invalid for other statuses. Students cannot change another student's recipient.

### 5.5 Submission and resubmission

The submission endpoint accepts text and optional file. File storage validates and saves the file; the domain service locks the recipient, checks ownership and active assignment status, inserts a submission attempt, and sets recipient status to submitted. The route commits; failure rolls back and removes the newly saved file.

**Key files:** `api/submissions.py`, `domains/submissions.py`, `storage/local.py`, `db/models.py`.

Database checks require either text or a complete file metadata set. Submission history supports multiple attempts and feedback association.

**Limitations:** local filesystem storage is not production object storage. Secure file download behavior needs review. Full submission UI is not connected at this revision.

### 5.6 Teacher review and feedback

Teacher routes list classroom submissions and submit review decisions with feedback. The service checks teacher membership, stores a Feedback row, and moves the recipient to completed or needs_revision. Student endpoints expose feedback and submission history.

**Key files:** `api/reviews.py`, `api/submissions.py`, `domains/reviews.py`, `domains/submissions.py`, `schemas/review.py`.

**Frontend status:** Submissions and Feedback pages are placeholders; backend endpoints do not mean the complete web review workflow is finished.

### 5.7 In-app notifications

Assignment creation creates notifications for recipients. A notification stores owner, type, title/message, optional related entity, JSON payload, and read timestamp. APIs list notifications, count unread items, and mark one/all read. Frontend displays notifications.

A notification record is not proof that a Telegram message was sent. No websocket/push delivery is established by inspected code.

### 5.8 Telegram reminder worker

The worker polls persisted due reminders, claims rows using row locks and `SKIP LOCKED`, marks them processing, increments attempt count, loads assignment/recipient/user/Telegram identity, then sends through Telegram Bot API. It marks success sent, retries eligible failures, or marks failed. It cancels reminders when assignment is no longer active or recipient has submitted/completed. Stale processing claims are recovered after a lease timeout.

**Why persisted reminders:** database rows survive process restarts; in-memory timers do not.  
**Why SKIP LOCKED:** multiple workers can claim different rows without processing the same reminder concurrently.

Run separately:
```powershell
cd backend
$env:PYTHONPATH="."
python -m app.workers.reminders
```

**Limitations:** TelegramIdentity must exist; a complete linking/verification flow is not confirmed. Worker is not started by FastAPI. Missing bot token causes delivery failure. No concrete Groq adapter module is present in the inspected integrations package.

### 5.9 Demo seed

`backend/scripts/seed_demo.py` creates SIM Demo Academy, one coordinator, two teachers, ten students, three classrooms, memberships, and welcome assignments. It runs only when APP_ENV is development/dev/local. It is additive/idempotent, does not delete records, and resets passwords only for reserved `@sim-demo.test` accounts. It refuses conflicting classroom role assignments.

Run:
```powershell
cd backend
$env:APP_ENV = "development"
$env:PYTHONPATH = "."
python -m scripts.seed_demo
```
See `backend/DEMO_ACCOUNTS.md` for demo credentials. Never reuse these credentials in production.

## 6. Technical decisions

| Choice | Reason | Trade-off |
|---|---|---|
| FastAPI | API-first Python service, validation, OpenAPI | Django offers more integrated admin features |
| React + TypeScript + Vite | Separate web client and fast dev loop | No server-rendered frontend |
| PostgreSQL | Transactions, constraints, concurrent workflows | SQLite is simpler but less representative |
| SQLAlchemy async | Async DB sessions and explicit transaction boundaries | More async/session complexity |
| Modular monolith | Clear domains without distributed deployment overhead | Not independently scalable services |
| JWT bearer auth | Fits stateless API requests | Token storage/refresh design needs production review |
| Per-student recipient rows | Independent progress and submission history | More relational rows and joins |
| School timezone | Deadlines follow school policy | Must validate timezone-aware input |
| Persisted reminder worker | Durable scheduling and retries | Separate process to operate |
| Local file storage | Simple development implementation | Replace with object storage for production |

### Interview explanations
- **Why not microservices?** The domain is evolving; a modular monolith is simpler to test, deploy, and transact while preserving module boundaries.
- **Why Assignment + AssignmentRecipient?** Task content is shared, progress belongs to each student.
- **Why domain services do not commit?** Route/worker owns the complete transaction, so assignment, recipients, reminders, and notifications succeed or roll back together.
- **Why school timezone?** Browser timezone may differ from school timezone; store a UTC instant after interpreting the deadline in the school timezone.

## 7. Constraints and limitations

1. Frontend submission, review, feedback, and progress workflows are incomplete.
2. Teacher/student switch is visual, not an authorization mechanism.
3. Student onboarding currently uses user UUID rather than email lookup/invitation.
4. Telegram account linking is not confirmed complete.
5. Groq settings/architecture references do not prove a working LLM integration.
6. Reminder worker must be run separately.
7. Local file storage is not a production storage solution.
8. localStorage JWT storage needs a production security review.
9. Some cross-table consistency rules are enforced in domain services rather than entirely by database constraints.
10. README/implementation plan may contain stale status notes.
11. Docker Compose configuration is not evidence of production deployment.
12. Test files exist, but this documentation task did not execute the complete suite on the exact source revision.

## 8. Setup, run, and test

### Prerequisites
Git, Python compatible with backend requirements (README says Python 3.12+), Node/npm, Docker Desktop/Compose, and PostgreSQL.

### Clone and branch
```powershell
git clone https://github.com/muralikrishna1729/sim-classroom-companion.git
cd sim-classroom-companion
git checkout feature/frontend-demo
git pull --ff-only origin feature/frontend-demo
```

### Backend environment
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```
Set `DATABASE_URL`, `JWT_SECRET_KEY`, `CORS_ORIGINS`, `APP_ENV`, and relevant timezone/Telegram settings. Never commit .env or secrets.

### PostgreSQL
```powershell
docker compose up -d db
docker ps
```
Compose default is host port 5432. In the development machine used in this project, that port was occupied, so the project DB was mapped to host port 5435. For that local override:
```text
postgresql+asyncpg://classroom_app:classroom_local_dev@localhost:5435/classroom_companion
```
Connect:
```powershell
docker exec -it sim-classroom-postgres psql -U classroom_app -d classroom_companion
```
Port 5435 is machine-specific, not the Compose default.

### Migrations and API
```powershell
cd backend
$env:PYTHONPATH = "."
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```
Port 8001 was used locally because 8000 was occupied. Health endpoints: `/health`, `/health/ready`; OpenAPI docs: `/docs`.

### Seed demo data
```powershell
$env:APP_ENV = "development"
$env:PYTHONPATH = "."
python -m scripts.seed_demo
```

### Frontend
```powershell
cd frontend
npm install
Copy-Item .env.example .env
```
Set `VITE_API_BASE_URL=http://localhost:8001/api/v1`, then:
```powershell
npm run dev
```
Open `http://localhost:5173`.

### Worker
In another terminal:
```powershell
cd backend
$env:PYTHONPATH = "."
python -m app.workers.reminders
```

### Tests/build
```powershell
$env:PYTHONPATH = "backend"
python -m pytest backend/tests -q
```
Frontend:
```powershell
cd frontend
npm run build
```

Suggested smoke test: teacher login → create Class 8-A assignment → student login → verify own assignment → submit → teacher review → student sees feedback. The latter UI steps require frontend work; use the API until those screens are implemented.

## 9. Concept glossary

Tags reflect topics already covered in project conversations. Familiar items receive a reminder; new/probably-new items are explained in context.

- **[FAMILIAR] FastAPI:** Python framework serving HTTP endpoints.
- **[FAMILIAR] Pydantic schema:** Validates request/response shapes.
- **[NEW] Dependency injection:** FastAPI calls dependencies such as `get_db` and `get_current_user` before a route, providing shared resources without repeating setup.
- **[FAMILIAR] REST:** HTTP methods and paths representing resources/actions.
- **[NEW] 401 vs 403:** 401 means authentication is missing/invalid; 403 means authenticated user lacks permission. Useful for diagnosing token vs membership failures.
- **[FAMILIAR] CORS:** Browser policy controlling allowed frontend origins.
- **[FAMILIAR] ORM:** SQLAlchemy maps Python classes to relational tables.
- **[NEW] AsyncSession:** Async SQLAlchemy session used for database operations in routes/services.
- **[NEW] Flush vs commit:** flush sends pending SQL inside the transaction; commit makes the transaction durable. Domain services flush; the route/worker commits.
- **[NEW] Row lock / FOR UPDATE:** Locks selected rows until transaction end to serialize updates to a recipient.
- **[NEW] SKIP LOCKED:** Lets concurrent workers skip rows claimed by another worker.
- **[FAMILIAR] Unique constraint:** Prevents duplicate values/combinations.
- **[NEW] Check constraint:** Database rule rejecting invalid row combinations, such as incomplete file metadata.
- **[NEW] Alembic migration:** Versioned database schema change; changing a model does not automatically update an existing DB.
- **[FAMILIAR] Enum:** Fixed set of allowed values.
- **[NEW] State machine:** Explicit allowed status transitions; prevents arbitrary status jumps.
- **[NEW] Unit of work:** Related database changes that must commit/rollback together.
- **[NEW] JWT:** Signed token containing claims such as user subject and expiry; backend verifies signature before trusting identity.
- **[NEW] Argon2id:** Password hashing algorithm designed to make guessing computationally expensive.
- **[PROBABLY NEW] localStorage trade-off:** Browser JavaScript can read stored tokens; an XSS flaw could expose them. Evaluate HttpOnly secure cookies for production.
- **[FAMILIAR] UTC:** Common reference time for storing instants.
- **[NEW] IANA timezone:** Named zone such as Asia/Kolkata with rules for interpreting local wall-clock time.
- **[NEW] Naive vs aware datetime:** Naive has no timezone; aware carries timezone/offset. Assignment deadlines must be aware to avoid ambiguous interpretation.
- **[FAMILIAR] React state/hooks:** Component state managed with hooks such as useState.
- **[FAMILIAR] TypeScript/Vite:** Static typing and frontend dev/build toolchain.
- **[NEW] API client wrapper:** `frontend/src/api.ts` centralizes URLs, token handling, endpoint calls, and response types.
- **[NEW] Background worker:** Separate process doing scheduled work outside the request/response path.
- **[NEW] Retry policy:** Reattempts failed delivery a bounded number of times, recording attempt count and error.
- **[NEW] Processing lease:** Timestamped claim that can be recovered if a worker crashes while processing.
- **[FAMILIAR] Telegram Bot API:** External API used to deliver reminders to linked chat IDs.

## 10. Remaining work

### P0 — Complete the core demo
1. Student submission UI (text and file).
2. Teacher submission list and review/feedback UI.
3. Student feedback and submission history UI.
4. Student progress controls and blocked-reason form.
5. End-to-end teacher → student → teacher → student test with seeded accounts.

### P1 — Onboarding and delivery
6. Replace UUID-only student add with email lookup/invitation.
7. Clarify coordinator/teacher permissions and membership management.
8. Implement and verify Telegram account linking.
9. Add worker health/observability and deployment instructions.
10. Confirm reminder behavior when deadlines change.

### P1 — Security and data integrity
11. Review JWT storage/session strategy.
12. Add password reset/email verification if required.
13. Add secure file download authorization and object storage.
14. Strengthen cross-table membership constraints where practical.
15. Review rate limits, upload policy, CORS, secrets, and logs before public deployment.

### P2 — AI and developer experience
16. If still in scope, implement a Groq adapter and validate structured output before domain operations.
17. Keep all authorization and persistence in domain services; never let an LLM write application state directly.
18. Reconcile README and implementation plan with actual code.
19. Add API examples, data dictionary, state transition reference, troubleshooting guide, and frontend/e2e tests.
20. Verify current GitHub Actions result and record it.

## 11. Open questions

1. Is Telegram-first interaction still the primary product goal, or is the React web app now the primary demo?
2. What exact natural-language actions should Groq support? No concrete adapter was found in the integrations package inspected.
3. What verified flow creates and confirms a user's TelegramIdentity?
4. What is the intended full invite lifecycle (create, redeem, expire, revoke)?
5. What endpoint and authorization policy should serve uploaded files to teachers/students?
6. What upload size and MIME types should production support?
7. Should coordinators see assignment progress/submissions across the whole school?
8. Can teachers edit assigned tasks, reopen cancelled tasks, or change deadlines?
9. Should reminders be one-time (currently created for 24 hours before due time) or configurable/multiple?
10. Is notification refresh sufficient, or is realtime delivery required?
11. What hosting, database, object storage, and Telegram transport are intended for production?
12. What are the latest full backend test and frontend build results for this exact branch head?
13. What is the latest GitHub Actions result?
14. What is the current local database state? Conversation history reported successful seeding, but this document cannot inspect the current machine.
15. Should the formal API reference be generated from the running OpenAPI schema?

---

## Appendix A — Debugging map

| Symptom | Inspect first | Typical cause |
|---|---|---|
| 401 | frontend API token handling; auth dependency; token expiry/secret | Missing, expired, invalid token |
| 403 on assignment | assignment domain; classroom membership | No active teacher membership |
| Timezone mismatch | assignment domain; selected school's timezone; frontend form | Browser timezone sent instead of school timezone |
| 422 | request schema and enum values | Wrong type/field/casing; target enum values are lowercase |
| Classroom list 500 | classroom domain query | Join/query/deduplication issue |
| Student cannot see assignment | recipient rows and student assignment query | Recipient missing or membership inactive |
| Reminder not sent | worker process, reminder status, bot token, TelegramIdentity | Worker not running or missing delivery prerequisites |
| UI shows placeholder | frontend App.tsx | Backend endpoint may exist; UI integration unfinished |

## Appendix B — Demo accounts

See `backend/DEMO_ACCOUNTS.md`. Demo credentials are local-development-only and must not be reused in production.

**Maintenance:** Update this document when APIs, domain rules, database models, setup steps, or frontend workflows change. Keep the source revision at the top aligned with the code being described.
