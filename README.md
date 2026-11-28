# SIM Classroom Companion

A Telegram-first classroom coordination application with a React web interface, a FastAPI backend, PostgreSQL persistence, and Groq-powered language understanding.

## Current status

**Phase 1 — Backend foundation.** This repository is being initialized incrementally. The initial backend commit provides application configuration, database connectivity, health endpoints, Docker-based local PostgreSQL, and a minimal test suite. Domain workflows will be added in separately reviewable changes.

## Architecture

- **Backend:** Python 3.12+, FastAPI, Pydantic Settings
- **Persistence:** PostgreSQL, SQLAlchemy 2.x (async), Alembic
- **Frontend (planned):** React + TypeScript + Vite
- **LLM integration (planned):** Groq, isolated behind an application adapter
- **Messaging (planned):** Telegram Bot API; long polling for local development
- **Scheduling (planned):** APScheduler with PostgreSQL-backed reminder records as the source of truth

The application is a modular monolith. Business rules belong in backend domain/application services; Telegram and the web API are delivery interfaces, not separate business-logic implementations.

## Local backend setup

1. Copy `backend/.env.example` to `backend/.env` and fill in local values. Do not commit this file.
2. Start PostgreSQL:

   ```bash
   docker compose up -d db
   ```

3. Create a Python 3.12 virtual environment and install dependencies:

   ```bash
   cd backend
   python -m venv .venv
   # Windows PowerShell: .venv\\Scripts\\Activate.ps1
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   cd ..
   ```

4. Run the API from the repository root:

   ```bash
   # Windows PowerShell
   $env:PYTHONPATH = "backend"
   # macOS/Linux
   export PYTHONPATH=backend

   uvicorn app.main:app --app-dir backend --reload
   ```

5. Verify:
   - `http://localhost:8000/health` — process health
   - `http://localhost:8000/health/ready` — database readiness
   - `http://localhost:8000/docs` — local OpenAPI docs

Run tests from the repository root with:

```bash
# Windows PowerShell
$env:PYTHONPATH = "backend"
# macOS/Linux
export PYTHONPATH=backend
pytest backend/tests
```

## Docker

After creating `backend/.env` from the example, `docker compose up --build` starts PostgreSQL and the API. The API container waits for the database health check before starting.

## Configuration and secrets

Never commit `backend/.env`, Telegram bot tokens, Groq API keys, database passwords, or other credentials. Use `.env.example` only for variable names and safe placeholders. The repository is public.

## Engineering rules

- Store timestamps in UTC; interpret and display user-facing deadlines in the school's configured IANA timezone.
- Enforce authorization and school/classroom scoping in the backend.
- Keep individual student progress on assignment-recipient records, not on the shared assignment.
- Treat database records as the source of truth for reminders; scheduled jobs must be safe to retry.
- Do not let an LLM directly write application state. Validate structured model output and route mutations through domain services.
- Add tests alongside each domain workflow and keep changes small enough to review.

## Project documentation

See [Architecture](docs/ARCHITECTURE.md), [Decision log](docs/DECISIONS.md), and [Implementation plan](docs/IMPLEMENTATION_PLAN.md).

## Frontend demo

The React + TypeScript frontend lives in `frontend/`.

### Run locally (Windows PowerShell)

1. Pull the demo branch:

   ```powershell
   git pull --ff-only origin feature/frontend-demo
   ```

2. In a new terminal, install and start the frontend:

   ```powershell
   cd frontend
   npm install
   Copy-Item .env.example .env
   npm run dev
   ```

3. Keep the FastAPI backend running in another terminal:

   ```powershell
   $env:PYTHONPATH = "backend"
   uvicorn app.main:app --app-dir backend --reload
   ```

4. Open `http://localhost:5173`.

The frontend calls the existing API at `http://localhost:8000/api/v1` by default. Override it with `VITE_API_BASE_URL` in `frontend/.env` if needed.

### Current demo scope

- Login and registration using the existing JWT endpoints.
- Classroom, assignment, and notification data loaded from the API.
- Teacher dashboard, classroom list, and class-wide assignment creation.
- Student-facing assignment overview and progress-ready UI.
- Responsive layout for desktop and mobile.

The teacher/student switch changes the visible workspace only; backend authorization remains authoritative. Use accounts with the corresponding classroom memberships to exercise teacher and student actions. Submission upload/review screens and Telegram account linking are subsequent iterations.
