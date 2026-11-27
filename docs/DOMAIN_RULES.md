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
- Group membership changes require an active teacher membership in the group's classroom, and the student must have an active student membership in that same classroom.

## Progress transitions

Student-owned progress transitions:

- pending -> acknowledged | in_progress
- acknowledged -> in_progress
- in_progress -> blocked
- blocked -> in_progress
- submitted -> completed (teacher review only)
- submitted -> needs_revision (teacher review only)
- needs_revision -> in_progress (student resumes work)
- completed -> no further transition

Submission is not a generic status update. It must go through the submission service, which locks the recipient row, verifies the authenticated actor is the assigned student, verifies the assignment is still assigned, validates text or complete file metadata, creates the submission and changes the recipient to submitted in the same transaction.

A blocked transition requires a non-empty reason. A blocked reason cannot be supplied for another status. Progress updates lock the recipient row to serialize concurrent changes.

Only the assigned student can use student-progress and submission operations. Teacher review transitions and feedback require a separate teacher-authorized service.

## Transaction ownership

Domain services flush changes but do not commit. The API or worker unit-of-work owns the transaction and must commit on success or roll back on failure. Assignment and recipient creation, and submission plus recipient-state update, must each occur in one transaction.

## Database constraints and service checks

Database unique constraints protect duplicate class memberships, group memberships, assignment recipients, Telegram identities and invite token hashes. Check constraints protect invite usage counts and reminder attempt counts.

Domain services enforce rules that the current foreign keys alone cannot prove: the actor's classroom role, student membership in the group's classroom, and the identity of the submission author. Before production, evaluate composite foreign keys or database constraints for cross-table classroom consistency and submission-author consistency. Service checks are not a substitute for transactionally enforced database integrity when multiple writers can modify the same records.
