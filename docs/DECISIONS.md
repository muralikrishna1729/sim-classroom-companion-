# Architecture Decision Log

## ADR-001 — FastAPI
Use FastAPI for the API-first application with a separate React client.

## ADR-002 — React + TypeScript + Vite
Use React for the web interface, with TypeScript and Vite for the client build workflow.

## ADR-003 — PostgreSQL
Use PostgreSQL for relational integrity and concurrent state changes across schools, classrooms, memberships, assignments, submissions and reminders.

## ADR-004 — Modular monolith
Keep one deployable backend with explicit domain and integration boundaries. Do not introduce microservices under the demonstration deadline.

## ADR-005 — Groq adapter
Use Groq as the available inference provider. Keep provider calls behind an adapter and validate structured outputs before passing proposals to domain services.

## ADR-006 — Persisted reminder records
PostgreSQL owns reminder state. A scheduler only triggers work; retries and duplicate protection must be based on persisted state and database constraints.

## ADR-007 — Scoped authorization
Authorize access using school membership and classroom role, not only a global role string. Enforce checks in backend services/routes.

## ADR-008 — Per-student assignment recipients
Track each student's acknowledgement and progress on a recipient entity. A shared assignment cannot have one progress state for an entire class.

## ADR-009 — Telegram long polling for local demo
Use long polling initially to avoid requiring a public webhook endpoint. Keep Telegram transport isolated so deployment can later switch to webhooks.

## ADR-010 — School timezone
Interpret and display deadlines using the school's configured IANA timezone; persist instants in UTC. Ask for clarification when a time is ambiguous.

## ADR-011 — Email/password web login plus Telegram linking
Web users authenticate using email/password. Telegram identity is linked to an existing student/teacher account through a verified invitation or linking flow.

## ADR-012 — Local file storage for development
Use a local upload directory initially with validation and controlled access. Keep file storage behind an abstraction so object storage can be introduced for public deployment.
