# PermitFlow — Phase 7: Organizer Tracking and Resubmission

**Status:** Completed
**Migration Head:** `e5b71d0c9a48` (unchanged — no migration required)
**Previous Test Count:** 218
**Current Test Count:** 288
**New Tests Added:** 70
**RLS Policies:** All seven policies preserved without modification.

---

## 1. Phase Objective

Phase 7 gave organizers the ability to see where their application stands with each
reviewing agency, correct an application that has been sent back, and resubmit it
without losing review work the agencies had already done.

The work builds directly on Phase 5 (submission and routing) and Phase 6 (reviewer
workflow and centralized lifecycle). No reviewer behaviour was changed: the reviewer
queue, decisions and history endpoints are untouched, and the only edit to
`api/app/api/reviews.py` was a bug fix to an audit action name (see 7.2).

## 2. Features Implemented

### 2.1 Organizer Tracking

`ApplicationResponse` gained a `reviews` field listing each required agency's review
task, so the existing list and detail endpoints now answer "where does this stand?"

Each entry carries the agency name, review status, the agency's comment, and both the
task's `created_at` and `updated_at`. Drafts return an empty list rather than `null`.

Reviewer identity is deliberately not exposed to organizers. It remains available in
the audit trail, where it belongs.

### 2.2 Editing After Changes Requested

`PUT /applications/{id}` now accepts applications in `Changes Requested`, in addition
to `Draft`. This was the single most restrictive rule left from Phase 6: an organizer
who was told "add a site plan" had no way to add one.

The existing `ApplicationWrite` schema still validates the payload, so editing
inherits the same field limits as creation. An edit records an `application.edited`
audit event naming each field that actually changed, with `old -> new` values.

An edit that changes nothing writes no event. Status is not editable.

### 2.3 Resubmission

`POST /applications/{id}/resubmit` is valid only from `Changes Requested`. It resets
review tasks selectively rather than restarting the whole review, which is the central
design decision of this phase:

| Task status before resubmission | After | Reason                                                   |
| -------------------------------- | ----- | -------------------------------------------------------- |
| `Changes Requested`             | `Pending` | The agency asked for something and has not seen the fix |
| `Approved`                      | `Approved` | The agency already said yes; not asked to earn it twice |
| `Pending`                       | `Pending` | Never asked anything; nothing to reset                 |
| `Rejected`                      | refused | A rejection has no reversal in this lifecycle          |

The comment on a reset task is cleared, because it described the previous submission
and leaving it on a `Pending` task would misattribute it as feedback about the
corrected one. The agency's actual words remain in the audit trail.

No review tasks are created or deleted. Routing is not re-evaluated, so the agency set
is stable across resubmission cycles.

The response reports which agencies were reset, preserved, and left pending, plus the
application with its derived status.

### 2.4 Derived Status After Resubmission

The application status is recomputed through the existing `resubmission_application_status`
helper rather than hardcoded to `Submitted`:

* All requested changes reset, no approval preserved → `Submitted`
* An approval preserved alongside a reset → `Under Review`

An approval that survived the resubmission means the application is not brand new, and
a frontend should not present it as a fresh submission.

### 2.5 Audit History for Organizers

`GET /applications/{id}/history` returns the full audit timeline to the owning
organizer. Same rows as the reviewer-scoped history, different question: that endpoint
is gated on a review assignment, this one on ownership.

Events are returned oldest first. Every event in the table is scoped to an application,
so there is nothing global to leak.

New audit actions:

| Action                    | `agency_id` | Meaning                                    |
| ------------------------- | ----------- | ------------------------------------------ |
| `application.edited`      | `NULL`      | Organizer changed fields on an application |
| `review.task_reset`       | set         | A task went from Changes Requested to Pending |
| `application.resubmitted` | `NULL`      | Organizer resubmitted                      |

Submission now also records an `application.status_changed` (`Draft -> Submitted`), so
an application's history begins at submission rather than being empty.

## 3. API Endpoints

| Method | Endpoint                        | Change | Description                                       |
| ------ | ------------------------------- | ------ | ------------------------------------------------- |
| GET    | `/applications`                 | changed | List now includes per-agency review progress     |
| GET    | `/applications/{id}`            | changed | Detail now includes per-agency review status     |
| PUT    | `/applications/{id}`            | changed | Accepts `Changes Requested` as well as `Draft`   |
| POST   | `/applications/{id}/resubmit`   | **new** | Selective reset of changes-requested tasks       |
| GET    | `/applications/{id}/history`    | **new** | Organizer-scoped audit timeline                  |

Unchanged from earlier phases: `POST /applications`, `POST /applications/{id}/submit`,
and the whole of `/review-tasks`.

### Authorization behavior

Inaccessible rows return 404 rather than 403, so the API does not confirm the existence
of another party's application. Wrong-role callers get 403, and missing authentication
gets 401. This matches the conventions established in Phases 5 and 6.

## 4. Files Changed

### New Files

| File                                  | Responsibility                                    |
| ------------------------------------- | ------------------------------------------------- |
| `api/tests/test_organizer_tracking.py` | 70 tests for tracking, editing, resubmission, history, isolation and concurrency |

### Modified Files

| File                              | Changes                                                                                 |
| --------------------------------- | -------------------------------------------------------------------------------------- |
| `api/app/core/lifecycle.py`       | Editable/resubmittable state sets, `assert_application_editable`, `assert_application_resubmittable`, `should_reset_on_resubmission`, `resubmission_application_status` |
| `api/app/schemas/application.py`  | `AgencyReviewStatus`, enriched `ApplicationResponse`, `ResubmitApplicationResponse`, `ApplicationHistoryResponse` |
| `api/app/api/applications.py`     | Resubmission and history routes, `Changes Requested` editing, audit writes, per-agency review loading |
| `api/app/api/reviews.py`          | Audit action name fix (7.2)                                                             |
| `api/tests/test_reviewer_workflow.py` | Updated audit-sequence expectations for the new submit event                    |

`lifecycle.py` remains the single source of status-transition truth. The new helpers
live there rather than in the route so they are testable independently of HTTP.

## 5. Database and Migration

**No migration was required.** The phase adds no columns, no tables and no constraints.
`AuditEvent.agency_id` was already added in Phase 6 and is reused for
`review.task_reset`; organizer-level events carry `NULL`.

Verification:

* `alembic check` → no new upgrade operations detected
* `alembic current` → `e5b71d0c9a48 (head)`
* All seven RLS policies unchanged, all seven tables still `FORCE ROW LEVEL SECURITY`

## 6. Testing and Verification

### Automated Tests

| Metric                | Result |
| --------------------- | -----: |
| Previous tests        |    218 |
| New tests             |     70 |
| Total tests passed    |    288 |
| Migration status      |  Clean |
| RLS policies modified |      0 |

The one warning is the pre-existing `InsecureKeyLengthWarning` from the deliberately
short forged JWT secret in `test_auth.py`.

### Test Coverage

The new tests cover per-agency tracking on list and detail, ownership and tenant
isolation on all four endpoints, editing in both editable states, refusal in the four
non-editable states, all six resubmission validity paths, selective reset for each task
status, rejection never being reopened, duplicate resubmission, required-field
validation on resubmit, audit contents and chronology, refused actions leaving no audit
trace, and three concurrency scenarios.

### Concurrency

Three tests cover simultaneous writers. The lock-order test is described in 7.3.

### Live Verification

Run over HTTP against a real uvicorn server and the seeded database, using the
restricted runtime role, so the RLS path was exercised rather than mocked.

| Scenario                                        | Observed result                |
| ----------------------------------------------- | ------------------------------ |
| Organizer sees per-agency status and comments     | Correct                        |
| Police requests changes, Health approves          | `Changes Requested`            |
| Organizer edits a Changes Requested application   | 200, status unchanged          |
| Resubmit — Police reset, Health preserved         | `Police` Pending, `Health` Approved |
| Derived status with a preserved approval          | `Under Review`                 |
| Duplicate resubmit                               | 409                            |
| Resubmit a Rejected application                  | 409, rejection not reopened    |
| Reviewer using organizer tracking                 | 403                            |
| Cross-tenant detail, history, edit, resubmit      | 404                            |
| Missing token                                    | 401                            |
| Never-edited draft history                        | Empty                          |

Audit history was verified to contain the expected eight-event sequence, with the
`review.task_reset` event correctly naming the Police agency and recording
`Changes Requested -> Pending`, and with the original request-changes comment still
present.

All temporary smoke data was removed, including a temporary Health reviewer account
created because seed data provides only one reviewer per tenant. Final counts: 2
tenants, 6 users, 6 agencies, 0 applications, 0 review tasks, 0 audit events, 16
routing rules. Seed data intact.

## 7. Important Engineering Decisions

### 7.1 Selective reset is the point

Restarting every review on resubmission would be simpler to implement and simpler to
explain, and it would also throw away approvals the agencies had already given. An
organizer fixing a site plan does not expect the health department to start over.

**Decision:** Reset only `Changes Requested`. `Approved` is preserved, `Pending` is left
alone, and `Rejected` blocks resubmission rather than being reopened.

### 7.2 Audit action name bug found in Phase 6 code

The reviewer decision path built its audit action from the enum *value*:
`f"review.{target.value.lower()}"`. Enum values are display labels, so a changes request
was recorded as `review.changes requested` — a name containing a space, inconsistent
with every other action in the table.

This was latent rather than visible: Phase 6 tests asserted against the same expression,
so they agreed with the bug.

**Decision:** Map enum members to dotted action names explicitly. Fixed to
`review.changes_requested`. This changes previously recorded data only for change
requests; the other two actions were unaffected.

### 7.3 Lock ordering between resubmission and reviewer decisions

Both paths take two locks: review tasks and the application row. The reviewer decision
path takes its own task first, then the application.

The initial resubmission implementation locked the application first, then the tasks.
This is an inverted order, and it can deadlock: a reviewer holding its task while
waiting for the application, and a resubmission holding the application while waiting
for the task. Postgres would abort one transaction with a deadlock error, surfacing to
the organizer as a 500.

**Decision:** Resubmission takes review tasks first, then the application, matching the
reviewer path.

The task query therefore runs before the ownership check. This is safe because RLS
scopes it to the caller's own tenant, so it cannot block another city; if the organizer
does not own the application the request 404s and the transaction rolls back, releasing
the locks.

This is enforced by a test that asserts the property directly: while a resubmission is
parked on a review task, the application row must still be obtainable by another
session. Verified to fail against the old ordering and pass against the new one.

The lock-order test initially hung the suite. The cause was the test's own probe
session holding the application row lock it had just acquired, which parked the
resubmission and made the thread-pool shutdown wait forever. Fixed by releasing the
probe before waiting on the request; no application code was involved.

### 7.4 Explicit flush before recomputation

Consistent with Phase 6: because `autoflush=False`, the session is explicitly flushed
after task resets and before the aggregate status is recomputed. Without it the
recalculation reads pre-reset values and derives the wrong status.

### 7.5 Rejected is refused rather than handled

A rejected task cannot coexist with `Changes Requested` in this lifecycle, so the case
is unreachable through the API. The code raises rather than assuming, so a future change
that makes it reachable fails loudly instead of silently reopening a rejection.

### 7.6 Routing is not re-evaluated on resubmission

Resubmission never creates or deletes review tasks. The agency set is fixed at first
submission and carried through resubmission cycles.

This is a deliberate scope decision. Re-deriving the agency set would mean an edit that
changed attendance across the Fire threshold, for instance, would add or remove a
review task mid-review — a larger behavioral change than the phase called for.

## 8. Security and Tenant Isolation

The existing architecture is preserved: JWT authentication, role-based authorization,
tenant-scoped sessions, PostgreSQL RLS, and ownership checks on `submitter_id`.

* Every new route resolves the application through the ownership-aware loader.
* Resubmission and history are organizer-only; reviewers and City Admins get 403.
* Cross-tenant access returns 404, matching earlier phases.
* RLS remains the isolation boundary; no policy was modified or added.
* Organizer-level audit events carry `agency_id = NULL`, since no single agency is the
  subject of an edit or a resubmission.

### Carried-over database integrity consideration

Unchanged from Phase 6: the `review_tasks` RLS policy validates `tenant_id` but does not
independently enforce that the referenced `agency_id` belongs to the same tenant. The
API path protects against this through RLS-scoped agency selection and an explicit
tenant-alignment check at submission. Worth addressing as database hardening, but not
in this phase, and not by weakening RLS.

## 9. Remaining Limitations

1. **Resubmission race returns 500.** A genuine concurrent double-submit can still
   surface an uncaught `IntegrityError` instead of 409. Same limitation as Phase 5 and
   Phase 6; the row locks make it very unlikely but not impossible.
2. **Routing not re-evaluated.** An edit that changes event type or crosses the Fire
   attendance threshold keeps the original agency set.
3. **No notification.** Agencies are not notified that a task was reset to `Pending`;
   a reviewer sees it on next login.
4. **No revision history of content.** The audit trail records which fields changed and
   their values, not a full snapshot of each submitted version.
5. **One reviewer per tenant in seed data.** Demonstrating a multi-agency flow requires
   creating an extra reviewer account.
6. **Admin routing UI.** Reviewer and agency setup still relies on seed data or manual
   creation.
7. **JWT test warning.** The pre-existing `InsecureKeyLengthWarning` in `test_auth.py`
   remains.
8. **No frontend.** This phase is backend only, as scoped.

## 10. Phase Completion Summary

Phase 7 delivered organizer tracking, editing after Changes Requested, selective
resubmission, and organizer-scoped audit history. Every Phase 6 limitation this phase
set out to address is now closed.

**Final verification: 288 tests passed, migration clean at `e5b71d0c9a48` with no new
migration required, all seven RLS policies preserved, live HTTP smoke test passed, and
seed data confirmed intact.**

### Next Planned Phase

Frontend implementation — an organizer-facing interface for drafts, submission,
tracking, editing and resubmission, built on the endpoints documented above.