# Architecture

## Shape

The system is a modular monolith: one FastAPI backend, one PostgreSQL database, and a React web client. Telegram is an additional delivery interface. Both web and Telegram entry points must call the same application/domain services.

```text
React Web ───────┐
                 ├── FastAPI ── Application/domain services ── PostgreSQL
Telegram Bot ────┘                       │
                                         ├── Groq adapter (interpretation only)
                                         └── Reminder scheduler / Telegram delivery
```

## Boundaries

- api/: HTTP routes, request/response schemas, dependency wiring.
- core/: settings, security primitives, shared application concerns.
- db/: SQLAlchemy base, engine, session lifecycle and migrations.
- domains/: domain models and application services grouped by capability.
- integrations/: Groq and Telegram adapters; external SDK details stay here.
- workers/: scheduled and retryable background work.

## Data and consistency

PostgreSQL is the source of truth. Assignment-level lifecycle is separate from per-student recipient progress. A reminder scheduler reads persisted reminder records and must be safe to retry; an in-memory schedule is not authoritative.

Store timestamps in UTC. Interpret natural-language dates in the school's configured IANA timezone. Enforce school and classroom access on the backend for every resource operation.

## AI boundary

Groq may interpret teacher/student language and return a validated structured proposal. It must not directly mutate records or decide authorization. Domain services validate actor permissions, state transitions, dates and business invariants before persistence.

## Local runtime

Docker Compose runs PostgreSQL and the API. Telegram uses long polling for the local demonstration. Public deployment can later switch Telegram transport to webhooks without moving business logic.
