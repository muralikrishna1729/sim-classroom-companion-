# Domain Rules

## Assignment targeting

Assignments are created for one classroom and resolved into individual recipient rows.

- CLASS: all active student memberships in the classroom at creation time.
- INDIVIDUAL: every explicitly selected user must be an active student member of that classroom.
- GROUP: every selected group must belong to that classroom; recipients are the distinct active student members across the selected groups.
- A student selected through more than one group receives one recipient row. One deterministic source group is retained for provenance.
- The database unique constraint on (assignment_id, student_id) is the final duplicate defense.
- The actor must have an active teacher membership in the target classroom.
- The school must be active and the assignment timezone must match its configured IANA timezone.
- A supplied deadline must be timezone-aware and is normalized to UTC before persistence.

## Progress transitions

Student-owned transitions are validated by the assignment domain service:

- pending -> acknowledged | in_progress
- acknowledged -> in_progress
- in_progress -> blocked | submitted
- blocked -> in_progress | submitted
- submitted -> needs_revision | completed
- needs_revision -> in_progress | submitted
- completed -> no further transition

A blocked transition requires a non-empty reason. A blocked reason cannot be supplied for another status. The service locks the recipient row while applying the transition.

Only the assigned student can use this student-progress operation. Teacher review transitions are separate and must be implemented in a teacher-authorized service.

## Transaction ownership

Domain services flush changes but do not commit. The API or worker unit-of-work owns the transaction and must commit on success or roll back on failure. Assignment and recipient creation must be performed in the same transaction.

## Remaining database-level integrity work

Some cross-table rules cannot be guaranteed by the current simple foreign keys alone, including ensuring a group member's class membership matches the group's classroom and ensuring a submission author matches the recipient student. The domain service checks are necessary, and composite foreign keys or carefully designed database constraints should be considered before production.
