# Local demo accounts

These accounts are created by `python -m scripts.seed_demo` in a development database only.

**Shared local demo password:** `ClassroomDemo!2026`

| Role | Email |
|---|---|
| Coordinator | coordinator@sim-demo.test |
| Teacher | teacher1@sim-demo.test |
| Teacher | teacher2@sim-demo.test |
| Student | student01@sim-demo.test |
| Student | student02@sim-demo.test |
| Student | student03@sim-demo.test |
| Student | student04@sim-demo.test |
| Student | student05@sim-demo.test |
| Student | student06@sim-demo.test |
| Student | student07@sim-demo.test |
| Student | student08@sim-demo.test |
| Student | student09@sim-demo.test |
| Student | student10@sim-demo.test |

The seed creates one school, three classrooms, active memberships, and one
welcome assignment per classroom. It is additive/idempotent and does not delete
existing data. It resets the password only for the reserved `@sim-demo.test`
accounts above when rerun.

Never use these credentials in production or expose a seeded development
database publicly.
