# PermitFlow — Phase 6: Agency Reviewer Workflow

**Status:** Completed
**Migration Head:** `e5b71d0c9a48`
**Previous Test Count:** 147
**Current Test Count:** 218
**New Tests Added:** 71
**RLS Policies:** All three existing policies preserved without modification.

---

## 1. Phase Objective

The objective of Phase 6 was to implement the Agency Reviewer Workflow, allowing authorized agency reviewers to access assigned applications, inspect application details, make review decisions, and maintain a reliable audit history.

The implementation builds on the existing authentication, tenant isolation, PostgreSQL Row-Level Security (RLS), application submission, and agency routing functionality.

The implementation also introduces centralized application lifecycle management and concurrency protection for simultaneous review decisions.

## 2. Features Implemented

### 2.1 Reviewer Queue

Implemented an authenticated reviewer queue.

* Reviewers can view applications assigned to their agency.
* Queue supports filtering by review status and event type.
* Pagination is supported.
* Tenant and agency scoping is enforced.
* Unauthorized users cannot access reviewer functionality.

### 2.2 Application Details

Reviewers can access the details of applications assigned to their agency.

Security behavior:

* Reviewers cannot access another agency's review task.
* Cross-tenant access is prevented.
* Applications without a matching agency assignment are not exposed.
* Application fields cannot be modified through review decision requests.

### 2.3 Review Decisions

Implemented three review actions:

| Action          | Purpose                                       |
| --------------- | --------------------------------------------- |
| Approve         | Agency approves the application               |
| Reject          | Agency rejects the application                |
| Request Changes | Agency asks the organizer to make corrections |

Every decision requires a non-empty comment.

The API rejects:

* Missing comments
* Empty comments
* Whitespace-only comments
* Unknown actions
* Invalid state transitions
* Repeated decisions on completed tasks
* Attempts to modify application fields through the decision schema

### 2.4 Centralized Application Lifecycle

Created `api/app/core/lifecycle.py` as the single location for application status transition decisions.

The lifecycle logic is independent of HTTP handling and is reusable.

Aggregate status behavior:

* **Approved:** All required agency reviews are approved.
* **Rejected:** Any required agency rejects the application.
* **Changes Requested:** A reviewer requests changes.
* **Under Review:** Review is still in progress.

The implementation was verified with a scenario where a request for changes takes precedence over an earlier approval, resulting in `Changes Requested`.

### 2.5 Audit Trail

Reviewer actions are recorded using the existing `audit_events` model.

Audit records include:

* Application
* Reviewer identity
* Agency
* Action
* Comment
* Timestamp

Added `agency_id` to the audit event model and database schema.

The reviewer history endpoint returns the audit timeline in chronological order.

Audit events are retained rather than silently overwritten or deleted.

---

## 3. API Endpoints

| Method | Endpoint                      | Description                                               |
| ------ | ----------------------------- | --------------------------------------------------------- |
| GET    | `/review-tasks`               | List assigned review tasks with filters and pagination    |
| GET    | `/review-tasks/{id}`          | Retrieve a review task with application details           |
| POST   | `/review-tasks/{id}/decision` | Submit Approve, Reject, or Request Changes                |
| GET    | `/review-tasks/{id}/history`  | Retrieve the application's reviewer-scoped audit timeline |

### Decision Request

The decision endpoint accepts:

* `action`
* `comment`

It returns the updated review task and aggregate application status.

---

## 4. Files Changed

### New Files

| File                                                             | Responsibility                                            |
| ---------------------------------------------------------------- | --------------------------------------------------------- |
| `api/app/core/lifecycle.py`                                      | Centralized application status transition logic           |
| `api/app/api/reviews.py`                                         | Reviewer queue, details, decisions, and history endpoints |
| `api/app/schemas/review.py`                                      | Request and response validation schemas                   |
| `api/alembic/versions/e5b71d0c9a48_agency_id_on_audit_events.py` | Database migration for audit agency association           |
| `api/tests/test_reviewer_workflow.py`                            | 71 reviewer workflow tests                                |

### Modified Files

| File                    | Changes                                        |
| ----------------------- | ---------------------------------------------- |
| `api/app/main.py`       | Registered reviewer router                     |
| `api/app/models.py`     | Added `AuditEvent.agency_id` and its index     |
| `api/tests/conftest.py` | Added `TenantFixture.add_reviewer_for(agency)` |

---

## 5. Database and Migration

New migration:

`e5b71d0c9a48_agency_id_on_audit_events`

Changes:

* Added agency association to audit events.
* Added the corresponding index.
* Preserved existing RLS policies.

Verification:

* Alembic migration check completed successfully.
* Database is at the expected migration head.
* All three existing RLS policies remained untouched.

---

## 6. Testing and Verification

### Automated Tests

| Metric                | Result |
| --------------------- | -----: |
| Previous tests        |    147 |
| New tests             |     71 |
| Total tests passed    |    218 |
| Migration status      |  Clean |
| RLS policies modified |      0 |

### Test Coverage

The new tests cover:

* Reviewer queue agency scoping
* Tenant isolation
* Queue filters
* Application detail access
* All three review actions
* Missing, blank, and whitespace-only comments
* Unknown action validation
* Rejection of application fields in decision payloads
* Unauthorized roles
* Missing authentication
* Reviewer without an agency
* Wrong agency access
* Cross-tenant access
* Aggregate application outcomes
* Invalid transitions
* Audit event contents and ordering
* Concurrent review decisions

### Live Verification

Using seeded Springfield and Riverton tenants:

| Scenario                             | Observed Result   |
| ------------------------------------ | ----------------- |
| Police approves                      | Under Review      |
| Health approves after Police         | Approved          |
| Blank comment                        | 422               |
| Health reviewer accesses Police task | 404               |
| Repeated decision                    | 409               |
| Organizer edits reviewed application | 409               |
| Request Changes after approval       | Changes Requested |

The audit timeline was verified with the expected review and application status events.

Temporary smoke-test data was cleaned up.

Final smoke-test database counts:

* Applications: 0
* Review tasks: 0
* Audit events: 0

Seed data remained intact.

---

## 7. Important Engineering Decisions and Bug Fixes

### 7.1 Concurrency Protection

An initial concurrency test used two threads attempting simultaneous approvals.

Both requests passed even after the application row lock was removed. The requests did not reliably collide, so the test was not actually proving the race condition was handled.

The test was redesigned to manufacture a deterministic collision:

1. A separate database session acquires `FOR UPDATE` on the application.
2. An approval is committed while holding the lock.
3. A second decision is started in another thread.
4. The second request must wait until the lock is released.
5. The aggregate status is then checked.

The test was confirmed to fail without the lock, producing `Under Review` instead of `Approved`, and pass with the lock.

**Decision:** Keep application row locking to protect aggregate status calculation from concurrent reviewer decisions.

### 7.2 Transaction-Local Tenant Context

An existing test helper used:

`set_config(..., false)`

This set the tenant context at session scope and allowed a pooled connection to retain the tenant ID after commit.

The existing test `test_missing_context_on_recycled_connection_errors_for_documented` detected this issue.

The helper was corrected to use transaction-local tenant context, matching the production `get_tenant_db` behavior.

**Decision:** Tenant context must remain transaction-local to avoid stale tenant identity leaking through pooled connections.

### 7.3 Explicit Flush Before Aggregate Recalculation

The initial implementation recalculated application status before flushing the review task update.

Because SQLAlchemy was configured with `autoflush=False`, the aggregate query read the previous task status. As a result, the last approval incorrectly left the application `Under Review`.

An explicit `session.flush()` was added before aggregate recalculation.

**Decision:** Persist pending task state within the transaction before computing the aggregate application status.

### 7.4 Duplicate Decision Protection

Duplicate protection is provided through:

* Review task status validation
* Application row locking
* Database uniqueness constraint

The unique constraint is a final integrity backstop.

---

## 8. Security and Tenant Isolation

The implementation preserves the existing security architecture:

* JWT authentication
* Role-based authorization
* Tenant-scoped database sessions
* PostgreSQL RLS
* Agency-specific reviewer access
* Application ownership and assignment checks
* Transaction-safe review decisions

All three existing RLS policies were left unchanged.

### Known Database-Level Integrity Consideration

The current review task RLS policy validates `tenant_id`, but does not independently enforce that the referenced `agency_id` belongs to the same tenant.

A direct database insert under a tenant-scoped database role can therefore create a task with a same-tenant task row referencing an agency from another tenant.

The API request path protects against this through RLS-scoped agency selection and explicit tenant alignment validation.

This remains a database-level hardening consideration and should be addressed carefully without weakening existing RLS protections.

---

## 9. Remaining Limitations

The following items are intentionally outside Phase 6:

1. **Organizer Resubmission:** Applications in `Changes Requested` cannot yet be edited or resubmitted.
2. **City Admin Routing UI:** Reviewer and agency setup currently relies on seed data/manual creation.
3. **Advanced Queue Filters:** Date range and submitter search are not implemented.
4. **Organizer Audit Timeline:** Audit events are available through reviewer-scoped history, but are not yet surfaced to organizers.
5. **IntegrityError Mapping:** A rare unique-constraint `IntegrityError` is not yet translated to HTTP 409 and could surface as 500.
6. **JWT Test Warning:** The existing `InsecureKeyLengthWarning` from a deliberately short forged JWT secret in `test_auth.py` remains unchanged.

---

## 10. Phase Completion Summary

Phase 6 successfully implemented the backend Agency Reviewer Workflow.

The system now supports agency-scoped review queues, application inspection, approval/rejection/change requests, centralized status aggregation, audit history, and concurrency-safe decisions.

**Final verification: 218 tests passed, migration clean at `e5b71d0c9a48`, and all three existing RLS policies preserved.**

### Next Planned Phase

Phase 7 — Organizer Resubmission and Application Tracking:

* Allow organizers to view agency-wise review status and comments.
* Permit editing after `Changes Requested`.
* Resubmit corrected applications.
* Reset only agencies that requested changes to `Pending`.
* Preserve approvals from agencies that already approved.
* Maintain audit history across resubmission cycles.
