# Phase 5 — Application Submission & Agency Routing

## Status

Completed

## Implementation

* Added `POST /applications/{id}/submit`.
* Implemented automatic agency routing based on event type.
* Added Fire agency override when attendance exceeds 5,000.
* Added duplicate review-task prevention.
* Added database unique constraint on `(application_id, agency_id)`.
* Implemented submission validation and transaction-safe task creation.
* Prevented editing and resubmission of already submitted applications.

## Files Added

* `api/app/core/routing.py`
* `api/tests/test_submit_application.py`
* `api/alembic/versions/c3d91a7f4e82_one_review_task_per_agency.py`

## Files Modified

* `api/app/models.py`
* `api/app/api/applications.py`
* `api/app/schemas/application.py`
* `api/tests/conftest.py`

## Verification

* 147 tests passed.
* Alembic check clean.
* Live submission flow verified for Springfield and Riverton.
* Attendance 4,999 and 5,000 routes to Police + Health.
* Attendance 5,001 and 20,000 routes to Fire + Police + Health.
* Duplicate submission returns 409.
* Incomplete application returns 422.
* Unauthorized roles return 403.
* Unauthenticated requests return 401.
* Cross-tenant application access returns 404.
* No duplicate review tasks or tenant mismatches found during verification.
* Temporary test records cleaned up; seed data preserved.

## Design Decisions

* Submission requires complete application data.
* Submitted applications cannot be edited.
* Database uniqueness constraint provides duplicate protection under concurrent requests.
* Existing RLS policies remain unchanged.

## Known Consideration

The current RLS policy does not independently enforce that a review task's agency belongs to the same tenant. The submission API currently validates agency selection. This relationship should be reviewed during final architecture hardening.

## Scope Not Yet Implemented

* Reviewer approval/rejection
* Request changes
* Resubmission
* Audit trail
* Notifications
* Dashboards
