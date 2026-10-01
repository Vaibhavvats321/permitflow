"""
app/core/lifecycle.py

The single place where application and review status transitions are decided.

The assignment is explicit about this: "Status transitions live in one place in
the backend, not scattered across routes or the UI." Every endpoint that can move
a status calls into this module, so the lifecycle can be read top to bottom and
changed in one edit.

Two distinct state machines live here:

  ReviewTask.status   PENDING -> APPROVED | REJECTED | CHANGES_REQUESTED
                                    ^                    |
                                    `---- resubmit -------+   (only for this one)

  Application.status  DRAFT -> SUBMITTED -> UNDER_REVIEW -> APPROVED
                            ^                  |        -> REJECTED
                            |                  `--------> CHANGES_REQUESTED
                            `--------- resubmit --------'

The application status is *derived* from its review tasks rather than set
independently. That is the only arrangement in which "Approved only when every
required agency has approved it" holds without every caller remembering to
check the others.

Resubmission is the one transition that runs *backwards*, and it is selective on
purpose. An agency that already approved said what it wanted; making the
organizer earn that approval a second time would be wasteful and would lose the
fact that the agency had already signed off. So only the agencies that actually
asked for changes go back to Pending, and their previous decision is preserved
in the audit trail rather than erased.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.models import ApplicationStatus, ReviewStatus


class InvalidStatusTransition(ValueError):
    """
    A status change that the lifecycle does not permit.

    A domain error, not an HTTP error: this module has no opinion about status
    codes. Routes translate it into 409.
    """


# ---------------------------------------------------------------------------
# Review task transitions
# ---------------------------------------------------------------------------

# A reviewer's decision is final. Once a task leaves PENDING it cannot be
# revisited by any reviewer; the record of what was decided is kept in
# review_tasks.comment and audit_events instead of being silently overwritten.
ALLOWED_REVIEW_TRANSITIONS: dict[ReviewStatus, frozenset[ReviewStatus]] = {
    ReviewStatus.PENDING: frozenset(
        {
            ReviewStatus.APPROVED,
            ReviewStatus.REJECTED,
            ReviewStatus.CHANGES_REQUESTED,
        }
    ),
    ReviewStatus.APPROVED: frozenset(),
    ReviewStatus.REJECTED: frozenset(),
    ReviewStatus.CHANGES_REQUESTED: frozenset(),
}

# The states an application may be in while agencies are still reviewing it.
# A draft cannot be approved by a reviewer, and an application that has reached
# a final outcome is closed to further decisions.
REVIEWABLE_APPLICATION_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.UNDER_REVIEW,
        ApplicationStatus.CHANGES_REQUESTED,
    }
)

# States in which the application is settled and no further reviewer action is
# accepted. Rejection in particular is decisive even if another agency still has
# a Pending task, because "Rejected if any agency rejects it" has no reversal.
FINAL_APPLICATION_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {ApplicationStatus.APPROVED, ApplicationStatus.REJECTED}
)

# ---------------------------------------------------------------------------
# Resubmission
# ---------------------------------------------------------------------------

# The only state an organizer can resubmit from. A draft has nothing to
# resubmit; Submitted and Under Review are still with the agencies; Approved and
# Rejected are settled.
RESUBMITTABLE_APPLICATION_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {ApplicationStatus.CHANGES_REQUESTED}
)

# The only review status that goes back to Pending on resubmission.
#
# Deliberately not "everything except Approved": an agency that asked for
# changes must look at the corrected application, whereas an agency that already
# approved has nothing outstanding and should not be asked again. Rejected is
# excluded for the same reason Approved is preserved — reopening a rejection
# would silently overturn a decision, and "Rejected if any agency rejects it" has
# no reversal.
RESETTABLE_REVIEW_STATUSES: frozenset[ReviewStatus] = frozenset(
    {ReviewStatus.CHANGES_REQUESTED}
)

# Statuses an application must be in for an organizer to edit it. A draft is the
# normal case; a changes-requested application is back with the organizer
# precisely so they can fix it. Everything else is either with the agencies or
# settled.
EDITABLE_APPLICATION_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {ApplicationStatus.DRAFT, ApplicationStatus.CHANGES_REQUESTED}
)


def can_act_on_task(status: ReviewStatus) -> bool:
    return bool(ALLOWED_REVIEW_TRANSITIONS.get(status, frozenset()))


def assert_review_transition_allowed(
    current: ReviewStatus, target: ReviewStatus
) -> None:
    """
    Refuse a reviewer decision that the lifecycle forbids.

    The practical case is a reviewer acting on a task that already has a
    decision: a retried request, or two reviewers of the same agency acting
    concurrently. Whichever arrives second is rejected rather than overwriting
    the first decision.
    """
    if target not in ALLOWED_REVIEW_TRANSITIONS.get(current, frozenset()):
        raise InvalidStatusTransition(
            f"Cannot change a review task from {ReviewStatus(current).value} "
            f"to {ReviewStatus(target).value}"
        )


def assert_application_reviewable(status: ApplicationStatus) -> None:
    """
    Refuse a reviewer action on an application that is not under review.

    This is the assignment's own example of an invalid transition, "approving an
    application still in Draft", generalised: a draft is not reviewable, and a
    settled application is closed.
    """
    if status not in REVIEWABLE_APPLICATION_STATUSES:
        raise InvalidStatusTransition(
            f"An application that is {ApplicationStatus(status).value} cannot be "
            f"reviewed; expected one of "
            f"{', '.join(sorted(ApplicationStatus(s).value for s in REVIEWABLE_APPLICATION_STATUSES))}"
        )


# ---------------------------------------------------------------------------
# Application status, derived from its review tasks
# ---------------------------------------------------------------------------


def aggregate_application_status(
    task_statuses: Iterable[ReviewStatus],
    *,
    current: ApplicationStatus,
) -> ApplicationStatus:
    """
    Derive an application's status from the decisions on its review tasks.

    Precedence, highest first:

      1. Rejected          any agency rejected it. Decisive and irreversible.
      2. Changes Requested any agency asked for changes; it goes back to the
                           organizer. Outranks approval, because the organizer
                           has to act even if every other agency said yes.
      3. Approved          every required agency approved it.
      4. Under Review      at least one decision exists but the outcome is open.
      5. unchanged         nothing has been decided yet, so the application stays
                           Submitted rather than jumping to Under Review on the
                           strength of an empty task list.

    `current` is only consulted in the last case. Everything else is a
    consequence of the decisions, which is what keeps the status from drifting
    out of agreement with the review tasks.
    """
    statuses = list(task_statuses)

    if not statuses:
        return current

    if any(s is ReviewStatus.REJECTED for s in statuses):
        return ApplicationStatus.REJECTED

    if any(s is ReviewStatus.CHANGES_REQUESTED for s in statuses):
        return ApplicationStatus.CHANGES_REQUESTED

    if all(s is ReviewStatus.APPROVED for s in statuses):
        return ApplicationStatus.APPROVED

    if any(s is not ReviewStatus.PENDING for s in statuses):
        return ApplicationStatus.UNDER_REVIEW

    return current


def application_status_changed(
    previous: ApplicationStatus, new: ApplicationStatus
) -> bool:
    """Whether a recomputed status actually differs from what was stored."""
    return previous is not new


# ---------------------------------------------------------------------------
# Organizer actions: edit and resubmit
# ---------------------------------------------------------------------------


def assert_application_editable(status: ApplicationStatus) -> None:
    """
    Refuse an edit to an application that is not the organizer's to change.

    The two editable states are Draft (never submitted) and Changes Requested
    (sent back to the organizer to be corrected). Submitted and Under Review are
    with the agencies: an edit there would change what they are reviewing without
    triggering a new review, and would make their recorded decision a statement
    about a document that no longer exists. Approved and Rejected are settled.
    """
    if status not in EDITABLE_APPLICATION_STATUSES:
        raise InvalidStatusTransition(
            f"An application that is {ApplicationStatus(status).value} cannot be "
            f"edited; expected one of "
            f"{', '.join(sorted(ApplicationStatus(s).value for s in EDITABLE_APPLICATION_STATUSES))}"
        )


def assert_application_resubmittable(status: ApplicationStatus) -> None:
    """
    Refuse a resubmission of an application that is not awaiting corrections.

    Changes Requested is the only state that means "the organizer has work to do
    and the agencies are waiting". Allowing this from Submitted or Under Review
    would let an organizer reset Pending review tasks without any agency having
    asked for it.
    """
    if status not in RESUBMITTABLE_APPLICATION_STATUSES:
        raise InvalidStatusTransition(
            f"An application that is {ApplicationStatus(status).value} cannot be "
            f"resubmitted; it must be "
            f"{ApplicationStatus.CHANGES_REQUESTED.value} first"
        )


def should_reset_on_resubmission(status: ReviewStatus) -> bool:
    """
    Whether a review task goes back to Pending when the application is resubmitted.

    Only the agencies that requested changes. An approval already given stands,
    and a rejection is never reopened.
    """
    return ReviewStatus(status) in RESETTABLE_REVIEW_STATUSES


def resubmission_application_status(
    task_statuses: Sequence[ReviewStatus],
) -> ApplicationStatus:
    """
    The application status after a resubmission resets the changes-requested tasks.

    Delegates to the same aggregation the reviewer path uses, so "approved only
    when every required agency has approved it" cannot be true on one path and
    false on the other.

    With no rejected task and at least one reset to Pending, this resolves to
    Submitted when every agency asked for changes (a clean restart) and to Under
    Review when some agency already approved (that approval still stands, so the
    application is not brand new). A rejected task cannot reach here — the
    lifecycle has no path back from Rejected — but if one somehow existed, the
    aggregate would still return Rejected rather than quietly reviving the
    application.
    """
    statuses = [ReviewStatus(s) for s in task_statuses]
    return aggregate_application_status(
        statuses, current=ApplicationStatus.SUBMITTED
    )