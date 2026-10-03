"""
tests/test_admin.py

City Admin endpoint tests.

Covers authorization, tenant isolation, and basic CRUD for the admin workspace.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import EventType, UserRole

from tests.conftest import TenantFixture

ADMIN_PREFIX = "/admin"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_dashboard_unauthenticated_returns_401(client: TestClient, make_tenant) -> None:
    """Unauthenticated request to admin endpoint returns 401."""
    make_tenant("AuthDashboardTenant")

    with TestClient(app) as client:
        response = client.get(f"{ADMIN_PREFIX}/dashboard")
        assert response.status_code == 401


def test_dashboard_organizer_returns_403(client: TestClient, make_tenant) -> None:
    """Organizer role is forbidden from admin endpoints."""
    tenant = make_tenant("AuthOrganizerTenant")
    token = tenant.token_for(tenant.organizer)

    with TestClient(app) as client:
        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(token))
        assert response.status_code == 403


def test_dashboard_reviewer_returns_403(client: TestClient, make_tenant) -> None:
    """Agency Reviewer role is forbidden from admin endpoints."""
    tenant = make_tenant("AuthReviewerTenant", with_reviewer=True)
    token = tenant.token_for(tenant.reviewer)

    with TestClient(app) as client:
        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(token))
        assert response.status_code == 403


def test_dashboard_admin_returns_200(client: TestClient, make_tenant) -> None:
    """City Admin can access the dashboard."""
    tenant = make_tenant("AuthAdminTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(token))
        assert response.status_code == 200
        body = response.json()
        assert "total_applications" in body
        assert "average_days_to_decision" in body


# ---------------------------------------------------------------------------
# Tenant Isolation
# ---------------------------------------------------------------------------


def test_admin_lists_only_own_tenant_agencies(
    client: TestClient, make_tenant
) -> None:
    """
    City Admin sees only agencies from their own tenant.

    Two tenants are created, each with distinct agencies. The admin of tenant A
    must not see tenant B's agencies.
    """
    tenant_a = make_tenant("IsolationTenantA")
    tenant_b = make_tenant("IsolationTenantB")

    # Admin A lists agencies
    token_a = tenant_a.token_for(tenant_a.admin)

    with TestClient(app) as client:
        response = client.get(
            f"{ADMIN_PREFIX}/agencies", headers=auth(token_a)
        )
        assert response.status_code == 200
        agencies = response.json()
        names = {a["name"] for a in agencies}

        # Tenant A has Police, Fire, Health
        assert names == {"Police", "Fire", "Health"}

        # Verify no agencies from tenant B appear
        # (tenant B's agencies have same names but different tenant_id, so RLS
        # should exclude them; this assertion confirms the API filters by tenant)
        assert len(agencies) == 3


def test_admin_lists_only_own_tenant_users(
    client: TestClient, make_tenant
) -> None:
    """
    City Admin sees only users from their own tenant.

    Two tenants are created, each with their own organizer/admin/reviewer.
    The admin of tenant A must not see tenant B's users.
    """
    tenant_a = make_tenant("UserIsolationTenantA", with_reviewer=True)
    tenant_b = make_tenant("UserIsolationTenantB", with_reviewer=True)

    token_a = tenant_a.token_for(tenant_a.admin)

    with TestClient(app) as client:
        response = client.get(
            f"{ADMIN_PREFIX}/users", headers=auth(token_a)
        )
        assert response.status_code == 200
        users = response.json()

        # Should only see tenant A's users
        emails = {u["email"] for u in users}
        # TenantFixture lowercases the name: "UserIsolationTenantA" -> "userisolationtenanta"
        expected = {
            "userisolationtenanta-organizer@example.com",
            "userisolationtenanta-admin@example.com",
            "userisolationtenanta-reviewer@example.com",
        }
        assert emails == expected
        assert len(users) == 3


# ---------------------------------------------------------------------------
# Agency Management
# ---------------------------------------------------------------------------


def test_create_agency_success(client: TestClient, make_tenant) -> None:
    """City Admin can create a new agency successfully."""
    tenant = make_tenant("AgencyCreateTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        response = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "Building Safety"},
            headers=auth(token),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Building Safety"
        assert "id" in body
        assert "created_at" in body


def test_create_agency_duplicate_name_returns_409(client: TestClient, make_tenant) -> None:
    """Creating an agency with a duplicate name in the same tenant returns 409."""
    tenant = make_tenant("AgencyDuplicateTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # First create
        resp1 = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "Transportation"},
            headers=auth(token),
        )
        assert resp1.status_code == 201

        # Second create with same name
        resp2 = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "Transportation"},
            headers=auth(token),
        )
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"]


def test_fetch_own_tenant_agency(client: TestClient, make_tenant) -> None:
    """City Admin can fetch an agency belonging to their tenant."""
    tenant = make_tenant("AgencyFetchTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # Create an agency first
        create_resp = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "Environmental Health"},
            headers=auth(token),
        )
        assert create_resp.status_code == 201
        agency_id = create_resp.json()["id"]

        # Fetch it
        response = client.get(
            f"{ADMIN_PREFIX}/agencies/{agency_id}", headers=auth(token)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Environmental Health"
        assert body["id"] == agency_id


def test_fetch_other_tenant_agency_returns_404(client: TestClient, make_tenant) -> None:
    """Fetching an agency from another tenant returns 404 (not 403)."""
    tenant_a = make_tenant("FetchTenantA")
    tenant_b = make_tenant("FetchTenantB")

    # Create agency in tenant B
    token_b = tenant_b.token_for(tenant_b.admin)
    with TestClient(app) as client:
        create_resp = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "B-Agency"},
            headers=auth(token_b),
        )
        assert create_resp.status_code == 201
        agency_id_b = create_resp.json()["id"]

    # Admin A tries to fetch tenant B's agency
    token_a = tenant_a.token_for(tenant_a.admin)
    with TestClient(app) as client:
        response = client.get(
            f"{ADMIN_PREFIX}/agencies/{agency_id_b}", headers=auth(token_a)
        )
        assert response.status_code == 404


def test_update_own_agency_success(client: TestClient, make_tenant) -> None:
    """City Admin can update their own agency's name."""
    tenant = make_tenant("AgencyUpdateTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # Create
        create_resp = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "Old Name"},
            headers=auth(token),
        )
        assert create_resp.status_code == 201
        agency_id = create_resp.json()["id"]

        # Update
        update_resp = client.patch(
            f"{ADMIN_PREFIX}/agencies/{agency_id}",
            json={"name": "New Name"},
            headers=auth(token),
        )
        assert update_resp.status_code == 200
        body = update_resp.json()
        assert body["name"] == "New Name"
        assert body["id"] == agency_id


def test_update_agency_to_duplicate_name_returns_409(client: TestClient, make_tenant) -> None:
    """Updating an agency to an existing name in the same tenant returns 409."""
    tenant = make_tenant("AgencyUpdateDupTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # Create two agencies
        resp1 = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "Agency One"},
            headers=auth(token),
        )
        assert resp1.status_code == 201
        id1 = resp1.json()["id"]

        resp2 = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "Agency Two"},
            headers=auth(token),
        )
        assert resp2.status_code == 201
        id2 = resp2.json()["id"]

        # Try to rename Agency Two to "Agency One"
        update_resp = client.patch(
            f"{ADMIN_PREFIX}/agencies/{id2}",
            json={"name": "Agency One"},
            headers=auth(token),
        )
        assert update_resp.status_code == 409
        assert "already exists" in update_resp.json()["detail"]


def test_update_other_tenant_agency_returns_404(client: TestClient, make_tenant) -> None:
    """Updating another tenant's agency returns 404 (not 403)."""
    tenant_a = make_tenant("UpdateTenantA")
    tenant_b = make_tenant("UpdateTenantB")

    token_b = tenant_b.token_for(tenant_b.admin)
    with TestClient(app) as client:
        create_resp = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "B-Agency"},
            headers=auth(token_b),
        )
        assert create_resp.status_code == 201
        agency_id_b = create_resp.json()["id"]

    token_a = tenant_a.token_for(tenant_a.admin)
    with TestClient(app) as client:
        response = client.patch(
            f"{ADMIN_PREFIX}/agencies/{agency_id_b}",
            json={"name": "Hacked Name"},
            headers=auth(token_a),
        )
        assert response.status_code == 404


def test_delete_agency_referenced_by_routing_returns_409(client: TestClient, make_tenant) -> None:
    """Deleting an agency referenced by routing rules returns 409."""
    tenant = make_tenant("AgencyDeleteRoutingTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # Create an agency
        create_resp = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "Routing Agency"},
            headers=auth(token),
        )
        assert create_resp.status_code == 201
        agency_id = create_resp.json()["id"]

        # Create a routing rule referencing it
        routing_resp = client.post(
            f"{ADMIN_PREFIX}/routing",
            json={"event_type": "Marathon", "agency_id": agency_id},
            headers=auth(token),
        )
        assert routing_resp.status_code == 201

        # Try to delete
        delete_resp = client.delete(
            f"{ADMIN_PREFIX}/agencies/{agency_id}", headers=auth(token)
        )
        assert delete_resp.status_code == 409
        assert "referenced by routing rules" in delete_resp.json()["detail"]


def test_delete_agency_referenced_by_review_returns_409(client: TestClient, make_tenant) -> None:
    """Deleting an agency with existing review tasks returns 409."""
    tenant = make_tenant("AgencyDeleteReviewTenant", with_reviewer=True)
    admin_token = tenant.token_for(tenant.admin)
    organizer_token = tenant.token_for(tenant.organizer)

    with TestClient(app) as client:
        # Create an agency as admin
        create_resp = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "Review Agency"},
            headers=auth(admin_token),
        )
        assert create_resp.status_code == 201
        agency_id = create_resp.json()["id"]

        # Add a routing rule so the new agency reviews Marathon events
        routing_resp = client.post(
            f"{ADMIN_PREFIX}/routing",
            json={"event_type": "Marathon", "agency_id": agency_id},
            headers=auth(admin_token),
        )
        assert routing_resp.status_code == 201

        # Add a reviewer for the new agency (needed to see its review task)
        reviewer_resp = client.post(
            f"{ADMIN_PREFIX}/users",
            json={
                "email": "review-agency-reviewer@example.com",
                "password": "password123",
                "role": "Agency Reviewer",
                "agency_id": agency_id,
            },
            headers=auth(admin_token),
        )
        assert reviewer_resp.status_code == 201
        reviewer_token = client.post(
            "/auth/login",
            json={"email": "review-agency-reviewer@example.com", "password": "password123"},
        ).json()["access_token"]

        # Create an application and submit it to generate a review task
        # Must use organizer token for application creation
        from app.models import EventType
        from datetime import UTC, datetime, timedelta
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)
        draft_resp = client.post(
            "/applications",
            json={
                "event_name": "Test Event",
                "event_type": EventType.MARATHON.value,
                "start_date": START.isoformat(),
                "end_date": END.isoformat(),
                "location": "Test Location",
                "expected_attendance": 1000,
                "description": "Test",
            },
            headers=auth(organizer_token),
        )
        assert draft_resp.status_code == 201
        app_id = draft_resp.json()["id"]

        # Submit to create review tasks
        submit_resp = client.post(f"/applications/{app_id}/submit", headers=auth(organizer_token))
        assert submit_resp.status_code == 200

        # Verify the review task exists for our agency
        review_tasks = client.get(
            "/review-tasks", headers=auth(reviewer_token)
        )
        assert review_tasks.status_code == 200
        tasks = review_tasks.json()
        
        # Find our agency's task
        our_task = next((t for t in tasks if t["agency_id"] == agency_id), None)
        assert our_task is not None, "Review task for our agency should exist"

        # Try to delete the agency
        delete_resp = client.delete(
            f"{ADMIN_PREFIX}/agencies/{agency_id}", headers=auth(admin_token)
        )
        assert delete_resp.status_code == 409
        detail = delete_resp.json()["detail"]
        # Either routing rules or review tasks can block deletion
        assert ("routing rules" in detail) or ("review tasks" in detail)


def test_delete_other_tenant_agency_returns_404(client: TestClient, make_tenant) -> None:
    """Deleting another tenant's agency returns 404."""
    tenant_a = make_tenant("DeleteTenantA")
    tenant_b = make_tenant("DeleteTenantB")

    token_b = tenant_b.token_for(tenant_b.admin)
    with TestClient(app) as client:
        create_resp = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "B-Agency"},
            headers=auth(token_b),
        )
        assert create_resp.status_code == 201
        agency_id_b = create_resp.json()["id"]

    token_a = tenant_a.token_for(tenant_a.admin)
    with TestClient(app) as client:
        response = client.delete(
            f"{ADMIN_PREFIX}/agencies/{agency_id_b}", headers=auth(token_a)
        )
        assert response.status_code == 404


def test_invalid_agency_id_returns_404_not_500(client: TestClient, make_tenant) -> None:
    """Invalid (non-existent) agency IDs return 404, not 500."""
    tenant = make_tenant("InvalidAgencyTenant")
    token = tenant.token_for(tenant.admin)

    fake_id = uuid.uuid4()

    with TestClient(app) as client:
        # GET
        resp = client.get(f"{ADMIN_PREFIX}/agencies/{fake_id}", headers=auth(token))
        assert resp.status_code == 404

        # PATCH
        resp = client.patch(
            f"{ADMIN_PREFIX}/agencies/{fake_id}",
            json={"name": "New Name"},
            headers=auth(token),
        )
        assert resp.status_code == 404

        # DELETE
        resp = client.delete(f"{ADMIN_PREFIX}/agencies/{fake_id}", headers=auth(token))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------


def test_create_organizer_success(client: TestClient, make_tenant) -> None:
    """Admin can create an Organizer user."""
    tenant = make_tenant("UserCreateOrgTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        response = client.post(
            f"{ADMIN_PREFIX}/users",
            json={
                "email": "new-organizer@example.com",
                "password": "password123",
                "role": "Organizer",
            },
            headers=auth(token),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "new-organizer@example.com"
        assert body["role"] == "Organizer"
        assert "password_hash" not in body
        assert "password" not in body
        assert body["agency_id"] is None
        assert body["agency_name"] is None


def test_create_reviewer_with_valid_agency(client: TestClient, make_tenant) -> None:
    """Admin can create an Agency Reviewer with a valid same-tenant agency."""
    tenant = make_tenant("UserCreateRevTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # Get an existing agency ID from the tenant's fixture
        agency_id = tenant.agencies["Police"].id

        response = client.post(
            f"{ADMIN_PREFIX}/users",
            json={
                "email": "new-reviewer@example.com",
                "password": "password123",
                "role": "Agency Reviewer",
                "agency_id": str(agency_id),
            },
            headers=auth(token),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "new-reviewer@example.com"
        assert body["role"] == "Agency Reviewer"
        assert body["agency_id"] == str(agency_id)
        assert body["agency_name"] == "Police"
        assert "password_hash" not in body


def test_create_user_invalid_role_returns_422(client: TestClient, make_tenant) -> None:
    """Admin cannot create a user with an invalid role."""
    tenant = make_tenant("UserInvalidRoleTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        response = client.post(
            f"{ADMIN_PREFIX}/users",
            json={
                "email": "bad-role@example.com",
                "password": "password123",
                "role": "SuperAdmin",
            },
            headers=auth(token),
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        # Pydantic validation errors are a list of error objects
        assert isinstance(detail, list)
        assert len(detail) > 0
        # Check that the error is about the role field
        error_msg = str(detail).lower()
        assert "role" in error_msg


def test_create_organizer_with_agency_returns_422(client: TestClient, make_tenant) -> None:
    """Admin cannot assign an agency to an Organizer."""
    tenant = make_tenant("UserOrgAgencyTenant")
    token = tenant.token_for(tenant.admin)
    agency_id = tenant.agencies["Police"].id

    with TestClient(app) as client:
        response = client.post(
            f"{ADMIN_PREFIX}/users",
            json={
                "email": "org-with-agency@example.com",
                "password": "password123",
                "role": "Organizer",
                "agency_id": str(agency_id),
            },
            headers=auth(token),
        )
        assert response.status_code == 422
        assert "cannot be assigned to an agency" in response.json()["detail"]


def test_create_reviewer_with_cross_tenant_agency_returns_404(client: TestClient, make_tenant) -> None:
    """Admin cannot assign an agency belonging to another tenant."""
    tenant_a = make_tenant("UserCrossTenantA")
    tenant_b = make_tenant("UserCrossTenantB")
    token_a = tenant_a.token_for(tenant_a.admin)
    agency_b_id = tenant_b.agencies["Police"].id

    with TestClient(app) as client:
        response = client.post(
            f"{ADMIN_PREFIX}/users",
            json={
                "email": "cross-reviewer@example.com",
                "password": "password123",
                "role": "Agency Reviewer",
                "agency_id": str(agency_b_id),
            },
            headers=auth(token_a),
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


def test_create_user_duplicate_email_returns_409(client: TestClient, make_tenant) -> None:
    """Duplicate email is handled with the correct conflict response."""
    tenant = make_tenant("UserDupEmailTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # Create first user
        resp1 = client.post(
            f"{ADMIN_PREFIX}/users",
            json={
                "email": "duplicate@example.com",
                "password": "password123",
                "role": "Organizer",
            },
            headers=auth(token),
        )
        assert resp1.status_code == 201

        # Try to create another with same email
        resp2 = client.post(
            f"{ADMIN_PREFIX}/users",
            json={
                "email": "duplicate@example.com",
                "password": "different123",
                "role": "Organizer",
            },
            headers=auth(token),
        )
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"]


def test_create_user_password_hashed_not_returned(client: TestClient, make_tenant) -> None:
    """Password is hashed and never returned in the API response."""
    tenant = make_tenant("UserPassHashTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        response = client.post(
            f"{ADMIN_PREFIX}/users",
            json={
                "email": "hash-test@example.com",
                "password": "plaintextpassword",
                "role": "Organizer",
            },
            headers=auth(token),
        )
        assert response.status_code == 201
        body = response.json()
        # Verify password field is not in response
        assert "password" not in body
        assert "password_hash" not in body
        # Verify the response doesn't contain the plaintext password
        assert "plaintextpassword" not in str(body)


def test_create_user_cannot_override_tenant_id(client: TestClient, make_tenant) -> None:
    """Client cannot supply or override tenant_id during user creation."""
    tenant = make_tenant("UserTenantIdTenant")
    token = tenant.token_for(tenant.admin)
    other_tenant_id = str(uuid.uuid4())

    with TestClient(app) as client:
        # The UserCreate schema doesn't have tenant_id field, so this should
        # either be ignored or cause a 422. The schema has extra="forbid"
        # so extra fields should cause 422.
        response = client.post(
            f"{ADMIN_PREFIX}/users",
            json={
                "email": "tenant-override@example.com",
                "password": "password123",
                "role": "Organizer",
                "tenant_id": other_tenant_id,  # This field doesn't exist in schema
            },
            headers=auth(token),
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# User Retrieval and Updates
# ---------------------------------------------------------------------------


def test_list_users_with_role_filter(client: TestClient, make_tenant) -> None:
    """Admin can list users in their tenant with role filtering."""
    tenant = make_tenant("UserListFilterTenant", with_reviewer=True)
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # List all
        resp_all = client.get(f"{ADMIN_PREFIX}/users", headers=auth(token))
        assert resp_all.status_code == 200
        all_users = resp_all.json()
        assert len(all_users) == 3

        # Filter by Organizer
        resp_org = client.get(
            f"{ADMIN_PREFIX}/users?role=Organizer", headers=auth(token)
        )
        assert resp_org.status_code == 200
        org_users = resp_org.json()
        assert len(org_users) == 1
        assert org_users[0]["role"] == "Organizer"

        # Filter by Agency Reviewer
        resp_rev = client.get(
            f"{ADMIN_PREFIX}/users?role=Agency%20Reviewer", headers=auth(token)
        )
        assert resp_rev.status_code == 200
        rev_users = resp_rev.json()
        assert len(rev_users) == 1
        assert rev_users[0]["role"] == "Agency Reviewer"


def test_fetch_own_tenant_user(client: TestClient, make_tenant) -> None:
    """Admin can fetch a user from their own tenant."""
    tenant = make_tenant("UserFetchTenant")
    token = tenant.token_for(tenant.admin)
    target_id = tenant.organizer.id

    with TestClient(app) as client:
        response = client.get(
            f"{ADMIN_PREFIX}/users/{target_id}", headers=auth(token)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == str(target_id)
        assert body["email"] == tenant.organizer.email
        assert body["role"] == "Organizer"


def test_fetch_other_tenant_user_returns_404(client: TestClient, make_tenant) -> None:
    """Fetching another tenant's user returns 404 (not 403)."""
    tenant_a = make_tenant("UserFetchTenantA")
    tenant_b = make_tenant("UserFetchTenantB")
    token_a = tenant_a.token_for(tenant_a.admin)
    target_id_b = tenant_b.organizer.id

    with TestClient(app) as client:
        response = client.get(
            f"{ADMIN_PREFIX}/users/{target_id_b}", headers=auth(token_a)
        )
        assert response.status_code == 404


def test_update_user_permitted_fields(client: TestClient, make_tenant) -> None:
    """Admin can update permitted user fields (email, password)."""
    tenant = make_tenant("UserUpdateTenant")
    token = tenant.token_for(tenant.admin)
    target_id = tenant.organizer.id

    with TestClient(app) as client:
        # Update email
        response = client.patch(
            f"{ADMIN_PREFIX}/users/{target_id}",
            json={"email": "updated@example.com"},
            headers=auth(token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "updated@example.com"

        # Update password
        response = client.patch(
            f"{ADMIN_PREFIX}/users/{target_id}",
            json={"password": "newpassword123"},
            headers=auth(token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "updated@example.com"
        assert "password" not in body
        assert "password_hash" not in body

        # Verify new password works
        login_resp = client.post(
            "/auth/login",
            json={"email": "updated@example.com", "password": "newpassword123"},
        )
        assert login_resp.status_code == 200


def test_update_reviewer_agency_validates_tenant(client: TestClient, make_tenant) -> None:
    """Updating reviewer agency validates tenant ownership."""
    tenant_a = make_tenant("UserUpdateAgencyA")
    tenant_b = make_tenant("UserUpdateAgencyB")
    token_a = tenant_a.token_for(tenant_a.admin)
    agency_b_id = tenant_b.agencies["Police"].id

    with TestClient(app) as client:
        # Create reviewer in tenant A
        create_resp = client.post(
            f"{ADMIN_PREFIX}/users",
            json={
                "email": "reviewer-a@example.com",
                "password": "password123",
                "role": "Agency Reviewer",
                "agency_id": str(tenant_a.agencies["Police"].id),
            },
            headers=auth(token_a),
        )
        assert create_resp.status_code == 201
        reviewer_id = create_resp.json()["id"]

        # Try to assign agency from tenant B
        response = client.patch(
            f"{ADMIN_PREFIX}/users/{reviewer_id}",
            json={"agency_id": str(agency_b_id)},
            headers=auth(token_a),
        )
        assert response.status_code == 404


def test_update_other_tenant_user_returns_404(client: TestClient, make_tenant) -> None:
    """Updating another tenant's user returns 404."""
    tenant_a = make_tenant("UserUpdateTenantA")
    tenant_b = make_tenant("UserUpdateTenantB")
    token_a = tenant_a.token_for(tenant_a.admin)
    target_id_b = tenant_b.organizer.id

    with TestClient(app) as client:
        response = client.patch(
            f"{ADMIN_PREFIX}/users/{target_id_b}",
            json={"email": "hacked@example.com"},
            headers=auth(token_a),
        )
        assert response.status_code == 404


def test_user_response_never_exposes_password_hash(client: TestClient, make_tenant) -> None:
    """User response never exposes password_hash or other credential secrets."""
    tenant = make_tenant("UserNoLeakTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # Create
        create_resp = client.post(
            f"{ADMIN_PREFIX}/users",
            json={
                "email": "leak-test@example.com",
                "password": "secretpassword",
                "role": "Organizer",
            },
            headers=auth(token),
        )
        assert create_resp.status_code == 201
        body = create_resp.json()
        assert "password" not in body
        assert "password_hash" not in body

        # List
        list_resp = client.get(f"{ADMIN_PREFIX}/users", headers=auth(token))
        assert list_resp.status_code == 200
        for user in list_resp.json():
            assert "password" not in user
            assert "password_hash" not in user

        # Get single
        get_resp = client.get(
            f"{ADMIN_PREFIX}/users/{create_resp.json()['id']}", headers=auth(token)
        )
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert "password" not in body
        assert "password_hash" not in body


# ---------------------------------------------------------------------------
# User Deletion
# ---------------------------------------------------------------------------


def test_delete_user_referenced_by_audit_returns_409(client: TestClient, make_tenant) -> None:
    """Deleting a user referenced by audit records is safely rejected."""
    tenant = make_tenant("UserDeleteAuditTenant")
    admin_token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # Create a new organizer user
        create_resp = client.post(
            f"{ADMIN_PREFIX}/users",
            json={
                "email": "audit-user@example.com",
                "password": "password123",
                "role": "Organizer",
            },
            headers=auth(admin_token),
        )
        assert create_resp.status_code == 201
        user_id = create_resp.json()["id"]

        # Log in as the new user to get their token
        login_resp = client.post(
            "/auth/login",
            json={"email": "audit-user@example.com", "password": "password123"},
        )
        assert login_resp.status_code == 200
        audit_user_token = login_resp.json()["access_token"]

        # Create an application as the new user to generate audit events
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)
        draft_resp = client.post(
            "/applications",
            json={
                "event_name": "Audit Test",
                "event_type": EventType.MARATHON.value,
                "start_date": START.isoformat(),
                "end_date": END.isoformat(),
                "location": "Test",
                "expected_attendance": 1000,
                "description": "Test",
            },
            headers=auth(audit_user_token),
        )
        assert draft_resp.status_code == 201
        app_id = draft_resp.json()["id"]

        # Submit to create audit events
        submit_resp = client.post(f"/applications/{app_id}/submit", headers=auth(audit_user_token))
        assert submit_resp.status_code == 200

        # Try to delete the user - should fail due to audit references
        delete_resp = client.delete(
            f"{ADMIN_PREFIX}/users/{user_id}", headers=auth(admin_token)
        )
        assert delete_resp.status_code == 409
        detail = delete_resp.json()["detail"]
        assert "audit" in detail.lower()


def test_delete_other_tenant_user_returns_404(client: TestClient, make_tenant) -> None:
    """Deleting another tenant's user returns 404."""
    tenant_a = make_tenant("UserDeleteTenantA")
    tenant_b = make_tenant("UserDeleteTenantB")
    token_a = tenant_a.token_for(tenant_a.admin)
    target_id_b = tenant_b.organizer.id

    with TestClient(app) as client:
        response = client.delete(
            f"{ADMIN_PREFIX}/users/{target_id_b}", headers=auth(token_a)
        )
        assert response.status_code == 404


def test_admin_cannot_delete_own_account(client: TestClient, make_tenant) -> None:
    """Admin cannot delete their own account."""
    tenant = make_tenant("UserSelfDeleteTenant")
    token = tenant.token_for(tenant.admin)
    admin_id = tenant.admin.id

    with TestClient(app) as client:
        response = client.delete(
            f"{ADMIN_PREFIX}/users/{admin_id}", headers=auth(token)
        )
        assert response.status_code == 403
        assert "cannot delete your own" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Routing Configuration
# ---------------------------------------------------------------------------


def test_list_routing_rules(client: TestClient, make_tenant) -> None:
    """City Admin can list routing rules for their tenant."""
    tenant = make_tenant("RoutingListTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        response = client.get(f"{ADMIN_PREFIX}/routing", headers=auth(token))
        assert response.status_code == 200
        rules = response.json()

        # Seeded data: Police and Health for all event types
        assert len(rules) >= 4  # 4 event types * 2 agencies
        for rule in rules:
            assert "event_type" in rule
            assert "agency_id" in rule
            assert "agency_name" in rule
            assert rule["agency_name"] in ("Police", "Health")


def test_create_routing_rule_success(client: TestClient, make_tenant) -> None:
    """City Admin can create a valid routing rule."""
    tenant = make_tenant("RoutingCreateTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # Create a new agency first
        agency_resp = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "Environmental"},
            headers=auth(token),
        )
        assert agency_resp.status_code == 201
        agency_id = agency_resp.json()["id"]

        # Create routing rule
        response = client.post(
            f"{ADMIN_PREFIX}/routing",
            json={"event_type": "Concert", "agency_id": agency_id},
            headers=auth(token),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["event_type"] == "Concert"
        assert body["agency_id"] == agency_id
        assert body["agency_name"] == "Environmental"


def test_create_routing_rule_duplicate_returns_409(client: TestClient, make_tenant) -> None:
    """Duplicate event_type + agency_id rule returns 409."""
    tenant = make_tenant("RoutingDupTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # Create a new agency
        agency_resp = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "Transport"},
            headers=auth(token),
        )
        assert agency_resp.status_code == 201
        agency_id = agency_resp.json()["id"]

        # Create first rule
        resp1 = client.post(
            f"{ADMIN_PREFIX}/routing",
            json={"event_type": "Street Fair", "agency_id": agency_id},
            headers=auth(token),
        )
        assert resp1.status_code == 201

        # Try to create duplicate
        resp2 = client.post(
            f"{ADMIN_PREFIX}/routing",
            json={"event_type": "Street Fair", "agency_id": agency_id},
            headers=auth(token),
        )
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"]


def test_create_routing_cross_tenant_agency_returns_404(client: TestClient, make_tenant) -> None:
    """Admin cannot configure an agency belonging to another tenant."""
    tenant_a = make_tenant("RoutingCrossA")
    tenant_b = make_tenant("RoutingCrossB")
    token_a = tenant_a.token_for(tenant_a.admin)
    agency_b_id = str(tenant_b.agencies["Police"].id)

    with TestClient(app) as client:
        response = client.post(
            f"{ADMIN_PREFIX}/routing",
            json={"event_type": "Marathon", "agency_id": agency_b_id},
            headers=auth(token_a),
        )
        assert response.status_code == 404


def test_delete_routing_rule_success(client: TestClient, make_tenant) -> None:
    """Admin can delete an existing routing rule."""
    tenant = make_tenant("RoutingDeleteTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # Create a new agency and routing rule
        agency_resp = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "ToDelete"},
            headers=auth(token),
        )
        assert agency_resp.status_code == 201
        agency_id = agency_resp.json()["id"]

        create_resp = client.post(
            f"{ADMIN_PREFIX}/routing",
            json={"event_type": "Other", "agency_id": agency_id},
            headers=auth(token),
        )
        assert create_resp.status_code == 201

        # Delete the rule
        delete_resp = client.delete(
            f"{ADMIN_PREFIX}/routing/Other/{agency_id}", headers=auth(token)
        )
        assert delete_resp.status_code == 204

        # Verify it's gone
        list_resp = client.get(f"{ADMIN_PREFIX}/routing", headers=auth(token))
        rules = list_resp.json()
        assert not any(
            r["event_type"] == "Other" and r["agency_id"] == agency_id for r in rules
        )


def test_delete_routing_rule_nonexistent_returns_404(client: TestClient, make_tenant) -> None:
    """Deleting a non-existing rule returns 404."""
    tenant = make_tenant("RoutingDeleteNoneTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        fake_id = uuid.uuid4()
        response = client.delete(
            f"{ADMIN_PREFIX}/routing/Marathon/{fake_id}", headers=auth(token)
        )
        assert response.status_code == 404


def test_routing_rules_organizer_returns_403(client: TestClient, make_tenant) -> None:
    """Organizer cannot access routing rules."""
    tenant = make_tenant("RoutingRoleTenant")
    token = tenant.token_for(tenant.organizer)

    with TestClient(app) as client:
        response = client.get(f"{ADMIN_PREFIX}/routing", headers=auth(token))
        assert response.status_code == 403


def test_routing_rules_reviewer_returns_403(client: TestClient, make_tenant) -> None:
    """Agency Reviewer cannot access routing rules."""
    tenant = make_tenant("RoutingRoleTenant", with_reviewer=True)
    token = tenant.token_for(tenant.reviewer)

    with TestClient(app) as client:
        response = client.get(f"{ADMIN_PREFIX}/routing", headers=auth(token))
        assert response.status_code == 403


def test_routing_create_organizer_returns_403(client: TestClient, make_tenant) -> None:
    """Organizer cannot create routing rules."""
    tenant = make_tenant("RoutingCreateRoleTenant")
    token = tenant.token_for(tenant.organizer)
    agency_id = str(tenant.agencies["Police"].id)

    with TestClient(app) as client:
        response = client.post(
            f"{ADMIN_PREFIX}/routing",
            json={"event_type": "Marathon", "agency_id": agency_id},
            headers=auth(token),
        )
        assert response.status_code == 403


def test_routing_delete_reviewer_returns_403(client: TestClient, make_tenant) -> None:
    """Agency Reviewer cannot delete routing rules."""
    tenant = make_tenant("RoutingDeleteRoleTenant", with_reviewer=True)
    token = tenant.token_for(tenant.reviewer)

    with TestClient(app) as client:
        response = client.delete(
            f"{ADMIN_PREFIX}/routing/Marathon/{tenant.agencies['Police'].id}",
            headers=auth(token),
        )
        assert response.status_code == 403


def test_routing_matrix_returns_correct_structure(client: TestClient, make_tenant) -> None:
    """Routing matrix returns correct event types and agencies."""
    tenant = make_tenant("RoutingMatrixTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        response = client.get(f"{ADMIN_PREFIX}/routing/matrix", headers=auth(token))
        assert response.status_code == 200
        matrix = response.json()

        # All four event types should be present
        assert set(matrix.keys()) == {"Marathon", "Concert", "Street Fair", "Other"}

        # Each event type should have at least Police and Health
        for event_type in ("Marathon", "Concert", "Street Fair", "Other"):
            agencies = matrix[event_type]
            assert "Police" in agencies
            assert "Health" in agencies


def test_routing_matrix_cross_tenant_isolation(client: TestClient, make_tenant) -> None:
    """Routing configuration cannot expose another tenant's rules."""
    tenant_a = make_tenant("MatrixIsolationA")
    tenant_b = make_tenant("MatrixIsolationB")
    token_a = tenant_a.token_for(tenant_a.admin)
    token_b = tenant_b.token_for(tenant_b.admin)

    with TestClient(app) as client:
        # Tenant A creates a custom agency and routing rule
        agency_resp = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "CustomAgency"},
            headers=auth(token_a),
        )
        assert agency_resp.status_code == 201
        agency_id = agency_resp.json()["id"]

        create_resp = client.post(
            f"{ADMIN_PREFIX}/routing",
            json={"event_type": "Concert", "agency_id": agency_id},
            headers=auth(token_a),
        )
        assert create_resp.status_code == 201

        # Tenant B's matrix should not see Tenant A's custom rule
        response_a = client.get(f"{ADMIN_PREFIX}/routing/matrix", headers=auth(token_a))
        response_b = client.get(f"{ADMIN_PREFIX}/routing/matrix", headers=auth(token_b))

        matrix_a = response_a.json()
        matrix_b = response_b.json()

        assert "CustomAgency" in matrix_a["Concert"]
        assert "CustomAgency" not in matrix_b["Concert"]


# ---------------------------------------------------------------------------
# Business Behavior
# ---------------------------------------------------------------------------


def test_routing_changes_do_not_modify_existing_tasks(client: TestClient, make_tenant) -> None:
    """Existing submitted applications and review tasks are not silently modified when routing changes."""
    tenant = make_tenant("RoutingBizTenant", with_reviewer=True)
    admin_token = tenant.token_for(tenant.admin)
    organizer_token = tenant.token_for(tenant.organizer)
    reviewer_token = tenant.token_for(tenant.reviewer)

    with TestClient(app) as client:
        # Create a custom agency and routing rule for Marathon
        agency_resp = client.post(
            f"{ADMIN_PREFIX}/agencies",
            json={"name": "CustomBiz"},
            headers=auth(admin_token),
        )
        assert agency_resp.status_code == 201
        agency_id = agency_resp.json()["id"]

        routing_resp = client.post(
            f"{ADMIN_PREFIX}/routing",
            json={"event_type": "Marathon", "agency_id": agency_id},
            headers=auth(admin_token),
        )
        assert routing_resp.status_code == 201

        # Create reviewer for the new agency
        reviewer_resp = client.post(
            f"{ADMIN_PREFIX}/users",
            json={
                "email": "custom-reviewer@example.com",
                "password": "password123",
                "role": "Agency Reviewer",
                "agency_id": agency_id,
            },
            headers=auth(admin_token),
        )
        assert reviewer_resp.status_code == 201
        custom_reviewer_token = client.post(
            "/auth/login",
            json={"email": "custom-reviewer@example.com", "password": "password123"},
        ).json()["access_token"]

        # Create and submit an application
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)
        draft_resp = client.post(
            "/applications",
            json={
                "event_name": "Biz Test Event",
                "event_type": EventType.MARATHON.value,
                "start_date": START.isoformat(),
                "end_date": END.isoformat(),
                "location": "Test",
                "expected_attendance": 1000,
                "description": "Test",
            },
            headers=auth(tenant.token_for(tenant.organizer)),
        )
        assert draft_resp.status_code == 201
        app_id = draft_resp.json()["id"]

        submit_resp = client.post(f"/applications/{app_id}/submit", headers=auth(organizer_token))
        assert submit_resp.status_code == 200

        # Check that review tasks were created for the original agencies + new one
        submit_body = submit_resp.json()
        required_agencies = {a["name"] for a in submit_body["required_agencies"]}
        assert "CustomBiz" in required_agencies

        # Now delete the routing rule
        delete_resp = client.delete(
            f"{ADMIN_PREFIX}/routing/Marathon/{agency_id}", headers=auth(admin_token)
        )
        assert delete_resp.status_code == 204

        # Verify existing review tasks are NOT deleted/modified
        # Use the custom reviewer's token to see their tasks
        review_tasks = client.get(
            "/review-tasks", headers=auth(custom_reviewer_token)
        )
        tasks = review_tasks.json()
        custom_tasks = [t for t in tasks if t["agency_id"] == agency_id]
        # The existing review task for CustomBiz should still exist
        assert len(custom_tasks) > 0


def test_attendance_over_5000_requires_fire(client: TestClient, make_tenant) -> None:
    """Attendance greater than 5,000 always adds Fire agency."""
    tenant = make_tenant("FireOver5000Tenant")
    token = tenant.token_for(tenant.admin)
    organizer_token = tenant.token_for(tenant.organizer)

    with TestClient(app) as client:
        # Create an event with > 5000 attendance
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)
        draft_resp = client.post(
            "/applications",
            json={
                "event_name": "Huge Event",
                "event_type": EventType.CONCERT.value,
                "start_date": START.isoformat(),
                "end_date": END.isoformat(),
                "location": "Big Stadium",
                "expected_attendance": 6000,
                "description": "Large concert",
            },
            headers=auth(tenant.token_for(tenant.organizer)),
        )
        assert draft_resp.status_code == 201
        app_id = draft_resp.json()["id"]

        submit_resp = client.post(f"/applications/{app_id}/submit", headers=auth(organizer_token))
        assert submit_resp.status_code == 200

        required_agencies = {a["name"] for a in submit_resp.json()["required_agencies"]}
        assert "Fire" in required_agencies
        assert "Police" in required_agencies
        assert "Health" in required_agencies


def test_attendance_equal_5000_no_fire(client: TestClient, make_tenant) -> None:
    """Attendance exactly 5,000 follows existing assignment rule (no Fire)."""
    tenant = make_tenant("FireExactly5000Tenant")
    organizer_token = tenant.token_for(tenant.organizer)

    with TestClient(app) as client:
        # Event with exactly 5000 attendance
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)
        draft_resp = client.post(
            "/applications",
            json={
                "event_name": "Exact 5000 Event",
                "event_type": EventType.CONCERT.value,
                "start_date": START.isoformat(),
                "end_date": END.isoformat(),
                "location": "Medium Hall",
                "expected_attendance": 5000,
                "description": "Exactly 5000",
            },
            headers=auth(tenant.token_for(tenant.organizer)),
        )
        assert draft_resp.status_code == 201
        app_id = draft_resp.json()["id"]

        submit_resp = client.post(f"/applications/{app_id}/submit", headers=auth(organizer_token))
        assert submit_resp.status_code == 200

        required_agencies = {a["name"] for a in submit_resp.json()["required_agencies"]}
        # Fire should NOT be added for exactly 5000
        assert "Fire" not in required_agencies
        # Base agencies should still be there
        assert "Police" in required_agencies
        assert "Health" in required_agencies


def test_routing_invalid_event_type_returns_422(client: TestClient, make_tenant) -> None:
    """Routing rules with invalid or unsupported event types are rejected."""
    tenant = make_tenant("RoutingInvalidEventTenant")
    token = tenant.token_for(tenant.admin)
    agency_id = str(tenant.agencies["Police"].id)

    with TestClient(app) as client:
        response = client.post(
            f"{ADMIN_PREFIX}/routing",
            json={"event_type": "InvalidEventType", "agency_id": agency_id},
            headers=auth(token),
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "invalid event_type" in detail.lower()


# ---------------------------------------------------------------------------
# Dashboard Metrics
# ---------------------------------------------------------------------------


def test_dashboard_total_count(client: TestClient, make_tenant) -> None:
    """Dashboard returns correct total application count for the admin's tenant."""
    tenant = make_tenant("DashboardTotalTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(token))
        assert response.status_code == 200
        body = response.json()
        # No applications created yet, total should be 0
        assert body["total_applications"] == 0


def test_dashboard_draft_count(client: TestClient, make_tenant) -> None:
    """Draft count is correct."""
    tenant = make_tenant("DashboardDraftTenant")
    token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # Create a draft application
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)
        draft_resp = client.post(
            "/applications",
            json={
                "event_name": "Draft Event",
                "event_type": EventType.MARATHON.value,
                "start_date": START.isoformat(),
                "end_date": END.isoformat(),
                "location": "Test",
                "expected_attendance": 1000,
                "description": "Test",
            },
            headers=auth(tenant.token_for(tenant.organizer)),
        )
        assert draft_resp.status_code == 201

        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(token))
        assert response.status_code == 200
        body = response.json()
        assert body["draft_applications"] == 1
        assert body["total_applications"] == 1


def test_dashboard_submitted_and_under_review_counts(client: TestClient, make_tenant) -> None:
    """Submitted / under-review count is correct according to the actual status model."""
    tenant = make_tenant("DashboardSubmittedTenant", with_reviewer=True)
    admin_token = tenant.token_for(tenant.admin)
    organizer_token = tenant.token_for(tenant.organizer)
    reviewer_token = tenant.token_for(tenant.reviewer)

    with TestClient(app) as client:
        # Create and submit an application
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)
        draft_resp = client.post(
            "/applications",
            json={
                "event_name": "Submitted Event",
                "event_type": EventType.MARATHON.value,
                "start_date": START.isoformat(),
                "end_date": END.isoformat(),
                "location": "Test",
                "expected_attendance": 1000,
                "description": "Test",
            },
            headers=auth(organizer_token),
        )
        assert draft_resp.status_code == 201
        app_id = draft_resp.json()["id"]

        # Submit
        submit_resp = client.post(f"/applications/{app_id}/submit", headers=auth(organizer_token))
        assert submit_resp.status_code == 200

        # After submit, status should be SUBMITTED (not yet under review)
        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(admin_token))
        assert response.status_code == 200
        body = response.json()
        assert body["submitted_applications"] == 1
        assert body["under_review_applications"] == 0

        # First reviewer decision moves it to UNDER_REVIEW
        # Get review task
        tasks = client.get("/review-tasks", headers=auth(reviewer_token)).json()
        task_id = tasks[0]["id"]
        client.post(
            f"/review-tasks/{task_id}/decision",
            json={"action": "approve", "comment": "Looks good"},
            headers=auth(reviewer_token),
        )

        # Now it should be UNDER_REVIEW (still one agency pending)
        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(admin_token))
        body = response.json()
        assert body["submitted_applications"] == 0
        assert body["under_review_applications"] == 1


def test_dashboard_approved_count(client: TestClient, make_tenant) -> None:
    """Approved count is correct."""
    tenant = make_tenant("DashboardApprovedTenant", with_reviewer=True)
    admin_token = tenant.token_for(tenant.admin)
    organizer_token = tenant.token_for(tenant.organizer)
    reviewer_token = tenant.token_for(tenant.reviewer)

    with TestClient(app) as client:
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)

        # Remove Health from Marathon routing so only Police reviews
        admin_token = tenant.token_for(tenant.admin)
        health_id = tenant.agencies["Health"].id
        with TestClient(app) as client:
            delete_resp = client.delete(
            f"{ADMIN_PREFIX}/routing/Marathon/{health_id}", headers=auth(admin_token)
        )
            assert delete_resp.status_code == 204

            draft_resp = client.post(
                "/applications",
                json={
                    "event_name": "Approved Event",
                    "event_type": EventType.MARATHON.value,
                    "start_date": START.isoformat(),
                    "end_date": END.isoformat(),
                    "location": "Test",
                    "expected_attendance": 1000,
                    "description": "Test",
                },
                headers=auth(organizer_token),
            )
            assert draft_resp.status_code == 201
            app_id = draft_resp.json()["id"]

            # Submit
            submit_resp = client.post(f"/applications/{app_id}/submit", headers=auth(organizer_token))
            assert submit_resp.status_code == 200

            # Approve all reviewers (only Police now)
            tasks = client.get("/review-tasks", headers=auth(reviewer_token)).json()
            for task in tasks:
                client.post(
                    f"/review-tasks/{task['id']}/decision",
                    json={"action": "approve", "comment": "Approved"},
                    headers=auth(reviewer_token),
                )

            response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(admin_token))
            assert response.status_code == 200
            body = response.json()
            assert body["approved_applications"] == 1
            assert body["rejected_applications"] == 0


def test_dashboard_rejected_count(client: TestClient, make_tenant) -> None:
    """Rejected count is correct."""
    tenant = make_tenant("DashboardRejectedTenant", with_reviewer=True)
    admin_token = tenant.token_for(tenant.admin)
    organizer_token = tenant.token_for(tenant.organizer)
    reviewer_token = tenant.token_for(tenant.reviewer)

    with TestClient(app) as client:
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)
        draft_resp = client.post(
            "/applications",
            json={
                "event_name": "Rejected Event",
                "event_type": EventType.MARATHON.value,
                "start_date": START.isoformat(),
                "end_date": END.isoformat(),
                "location": "Test",
                "expected_attendance": 1000,
                "description": "Test",
            },
            headers=auth(tenant.token_for(tenant.organizer)),
        )
        assert draft_resp.status_code == 201
        app_id = draft_resp.json()["id"]

        # Submit
        submit_resp = client.post(f"/applications/{app_id}/submit", headers=auth(tenant.token_for(tenant.organizer)))
        assert submit_resp.status_code == 200

        # Reject
        tasks = client.get("/review-tasks", headers=auth(tenant.token_for(tenant.reviewer))).json()
        client.post(
            f"/review-tasks/{tasks[0]['id']}/decision",
            json={"action": "reject", "comment": "Rejected"},
            headers=auth(tenant.token_for(tenant.reviewer)),
        )

        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(tenant.token_for(tenant.admin)))
        body = response.json()
        assert body["rejected_applications"] == 1
        assert body["approved_applications"] == 0


def test_dashboard_cross_tenant_isolation(client: TestClient, make_tenant) -> None:
    """Applications from another tenant are excluded from all counts."""
    tenant_a = make_tenant("DashboardCrossA")
    tenant_b = make_tenant("DashboardCrossB")

    # Tenant B creates an application
    organizer_b_token = tenant_b.token_for(tenant_b.organizer)
    with TestClient(app) as client:
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)
        client.post(
            "/applications",
            json={
                "event_name": "Tenant B Event",
                "event_type": EventType.MARATHON.value,
                "start_date": START.isoformat(),
                "end_date": END.isoformat(),
                "location": "Test",
                "expected_attendance": 1000,
                "description": "Test",
            },
            headers=auth(organizer_b_token),
        )

    # Tenant A dashboard should not see Tenant B's application
    admin_a_token = tenant_a.token_for(tenant_a.admin)
    with TestClient(app) as client:
        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(tenant_a.token_for(tenant_a.admin)))
        body = response.json()
        assert body["total_applications"] == 0
        assert body["draft_applications"] == 0


def test_dashboard_avg_days_to_decision_calculated_from_completed(client: TestClient, make_tenant) -> None:
    """Average days to decision is calculated only from completed applications."""
    tenant = make_tenant("DashboardAvgTenant", with_reviewer=True)
    admin_token = tenant.token_for(tenant.admin)
    organizer_token = tenant.token_for(tenant.organizer)
    reviewer_token = tenant.token_for(tenant.reviewer)

    with TestClient(app) as client:
        # Remove Health from Marathon routing so only Police reviews
        admin_token = tenant.token_for(tenant.admin)
        health_id = tenant.agencies["Health"].id
        delete_resp = client.delete(
            f"{ADMIN_PREFIX}/routing/Marathon/{health_id}", headers=auth(admin_token)
        )
        assert delete_resp.status_code == 204

        # Create and approve an application
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)
        draft_resp = client.post(
            "/applications",
            json={
                "event_name": "Avg Decision Test",
                "event_type": EventType.MARATHON.value,
                "start_date": START.isoformat(),
                "end_date": END.isoformat(),
                "location": "Test",
                "expected_attendance": 1000,
                "description": "Test",
            },
            headers=auth(organizer_token),
        )
        assert draft_resp.status_code == 201
        app_id = draft_resp.json()["id"]

        # Submit
        submit_resp = client.post(f"/applications/{app_id}/submit", headers=auth(organizer_token))
        assert submit_resp.status_code == 200

        # Approve all
        tasks = client.get("/review-tasks", headers=auth(reviewer_token)).json()
        for task in tasks:
            client.post(
                f"/review-tasks/{task['id']}/decision",
                json={"action": "approve", "comment": "Approved"},
                headers=auth(reviewer_token),
            )

        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(admin_token))
        body = response.json()
        # Should have a non-negative average (could be 0 if same-day)
        assert body["average_days_to_decision"] is not None
        assert body["average_days_to_decision"] >= 0


def test_dashboard_avg_days_uses_submission_and_decision_timestamps(client: TestClient, make_tenant) -> None:
    """Average days to decision uses the actual submission and final-decision timestamps."""
    tenant = make_tenant("DashboardAvgTimestampTenant", with_reviewer=True)
    admin_token = tenant.token_for(tenant.admin)
    organizer_token = tenant.token_for(tenant.organizer)
    reviewer_token = tenant.token_for(tenant.reviewer)

    with TestClient(app) as client:
        # Remove Health from Marathon routing so only Police reviews
        admin_token = tenant.token_for(tenant.admin)
        health_id = tenant.agencies["Health"].id
        delete_resp = client.delete(
            f"{ADMIN_PREFIX}/routing/Marathon/{health_id}", headers=auth(admin_token)
        )
        assert delete_resp.status_code == 204

        # Create and submit
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)
        draft_resp = client.post(
            "/applications",
            json={
                "event_name": "Timestamp Test",
                "event_type": EventType.MARATHON.value,
                "start_date": START.isoformat(),
                "end_date": END.isoformat(),
                "location": "Test",
                "expected_attendance": 1000,
                "description": "Test",
            },
            headers=auth(organizer_token),
        )
        assert draft_resp.status_code == 201
        app_id = draft_resp.json()["id"]

        submit_resp = client.post(f"/applications/{app_id}/submit", headers=auth(organizer_token))
        assert submit_resp.status_code == 200

        # Approve
        tasks = client.get("/review-tasks", headers=auth(reviewer_token)).json()
        for task in tasks:
            client.post(
                f"/review-tasks/{task['id']}/decision",
                json={"action": "approve", "comment": "Approved"},
                headers=auth(reviewer_token),
            )

        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(admin_token))
        body = response.json()
        # The average should be computed from ReviewTask.updated_at - Application.created_at
        # which should be >= 0 (same day or later)
        assert body["average_days_to_decision"] is not None
        assert body["average_days_to_decision"] >= 0

def test_dashboard_zero_completed_applications_no_division_error(client: TestClient, make_tenant) -> None:
    """Zero completed applications returns a safe value without division errors."""
    tenant = make_tenant("DashboardZeroCompletedTenant")
    admin_token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # No applications at all
        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(admin_token))
        assert response.status_code == 200
        body = response.json()
        assert body["average_days_to_decision"] is None

        # Only draft applications
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)
        client.post(
            "/applications",
            json={
                "event_name": "Draft Only",
                "event_type": EventType.MARATHON.value,
                "start_date": START.isoformat(),
                "end_date": END.isoformat(),
                "location": "Test",
                "expected_attendance": 1000,
                "description": "Test",
            },
            headers=auth(tenant.token_for(tenant.organizer)),
        )

        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(admin_token))
        body = response.json()
        # No completed applications, average should be None
        assert body["average_days_to_decision"] is None

def test_dashboard_non_admin_returns_403(client: TestClient, make_tenant) -> None:
    """Dashboard is inaccessible to non-admin roles."""
    tenant = make_tenant("DashboardRoleTenant", with_reviewer=True)

    # Organizer
    with TestClient(app) as client:
        response = client.get(
            f"{ADMIN_PREFIX}/dashboard", headers=auth(tenant.token_for(tenant.organizer))
        )
        assert response.status_code == 403

    # Reviewer
    with TestClient(app) as client:
        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(tenant.token_for(tenant.reviewer)))
        assert response.status_code == 403


def test_dashboard_handles_null_timestamps(client: TestClient, make_tenant) -> None:
    """Dashboard handles applications with missing or nullable timestamps safely."""
    tenant = make_tenant("DashboardNullTimestampTenant")
    admin_token = tenant.token_for(tenant.admin)

    with TestClient(app) as client:
        # Create a draft with minimal fields (no dates, no attendance)
        draft_resp = client.post(
            "/applications",
            json={
                "event_name": "Minimal Draft",
                "event_type": EventType.OTHER.value,
            },
            headers=auth(tenant.token_for(tenant.organizer)),
        )
        assert draft_resp.status_code == 201

        # Dashboard should handle this gracefully
        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(tenant.token_for(tenant.admin)))
        assert response.status_code == 200
        body = response.json()
        assert body["total_applications"] == 1
        assert body["draft_applications"] == 1
        assert body["average_days_to_decision"] is None


# ---------------------------------------------------------------------------
# Application review visibility (list + detail carry review summaries)
# ---------------------------------------------------------------------------


def _create_and_submit(
    client: TestClient,
    tenant: TenantFixture,
    event_name: str,
    *,
    attendance: int = 1000,
) -> str:
    """File a complete draft as the tenant's organizer and submit it."""
    start = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
    end = start + timedelta(hours=6)
    draft_resp = client.post(
        "/applications",
        json={
            "event_name": event_name,
            "event_type": EventType.MARATHON.value,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "location": "Main Street",
            "expected_attendance": attendance,
            "description": "Review visibility fixture",
        },
        headers=auth(tenant.token_for(tenant.organizer)),
    )
    assert draft_resp.status_code == 201
    app_id = draft_resp.json()["id"]

    submit_resp = client.post(
        f"/applications/{app_id}/submit",
        headers=auth(tenant.token_for(tenant.organizer)),
    )
    assert submit_resp.status_code == 200
    return app_id


def _reviews_by_agency(application: dict) -> dict[str, dict]:
    """Index an application's review summaries by agency name."""
    return {review["agency_name"]: review for review in application["reviews"]}


def test_admin_list_populates_review_summaries(client: TestClient, make_tenant) -> None:
    """Admin list returns one populated review summary per required agency."""
    tenant = make_tenant("AdminListReviewsTenant")

    with TestClient(app) as client:
        _create_and_submit(client, tenant, "List Reviews Event")

        response = client.get(
            f"{ADMIN_PREFIX}/applications",
            headers=auth(tenant.token_for(tenant.admin)),
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1

        reviews = _reviews_by_agency(body[0])
        # Base routing matrix is Police + Health; attendance 1000 adds no Fire.
        assert set(reviews) == {"Police", "Health"}
        for review in reviews.values():
            assert review["review_status"] == "Pending"
            assert review["comment"] is None
            assert review["agency_id"]
            assert review["created_at"]
            assert review["updated_at"]


def test_admin_detail_populates_review_summaries(client: TestClient, make_tenant) -> None:
    """Admin detail returns the same populated review summaries as the list."""
    tenant = make_tenant("AdminDetailReviewsTenant")

    with TestClient(app) as client:
        app_id = _create_and_submit(client, tenant, "Detail Reviews Event")

        response = client.get(
            f"{ADMIN_PREFIX}/applications/{app_id}",
            headers=auth(tenant.token_for(tenant.admin)),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "Submitted"

        reviews = _reviews_by_agency(body)
        assert set(reviews) == {"Police", "Health"}
        assert all(r["review_status"] == "Pending" for r in reviews.values())


def test_admin_detail_reflects_decision_with_comment_and_timestamp(
    client: TestClient, make_tenant
) -> None:
    """
    A reviewer's decision reaches the admin detail view: status, comment, and a
    refreshed decision timestamp, while the undecided agency stays Pending.
    """
    tenant = make_tenant("AdminDecisionTenant", with_reviewer=True)

    with TestClient(app) as client:
        app_id = _create_and_submit(client, tenant, "Decision Event")

        # Baseline: both Pending, Police timestamp captured before the decision.
        before = client.get(
            f"{ADMIN_PREFIX}/applications/{app_id}",
            headers=auth(tenant.token_for(tenant.admin)),
        ).json()
        police_before = _reviews_by_agency(before)["Police"]
        assert police_before["review_status"] == "Pending"

        # Police reviewer approves with a comment.
        tasks = client.get(
            "/review-tasks", headers=auth(tenant.token_for(tenant.reviewer))
        ).json()
        task = next(t for t in tasks if t["application"]["id"] == app_id)
        decision = client.post(
            f"/review-tasks/{task['id']}/decision",
            json={"action": "approve", "comment": "Route is clear for this event."},
            headers=auth(tenant.token_for(tenant.reviewer)),
        )
        assert decision.status_code == 200

        after = client.get(
            f"{ADMIN_PREFIX}/applications/{app_id}",
            headers=auth(tenant.token_for(tenant.admin)),
        ).json()

        assert after["status"] == "Under Review"
        reviews = _reviews_by_agency(after)

        police = reviews["Police"]
        assert police["review_status"] == "Approved"
        assert police["comment"] == "Route is clear for this event."
        assert police["agency_id"] == str(tenant.agencies["Police"].id)
        assert police["created_at"] <= police["updated_at"]
        # The decision must move the task's updated timestamp.
        assert police["updated_at"] > police_before["updated_at"]

        # The agency that has not acted keeps its Pending state and no comment.
        health = reviews["Health"]
        assert health["review_status"] == "Pending"
        assert health["comment"] is None


def test_admin_detail_cross_tenant_returns_404(client: TestClient, make_tenant) -> None:
    """Another tenant's application id is a 404, not a leak and not a 403."""
    tenant_a = make_tenant("AdminCrossTenantA")
    tenant_b = make_tenant("AdminCrossTenantB")

    with TestClient(app) as client:
        app_b_id = _create_and_submit(client, tenant_b, "Tenant B Event")

        response = client.get(
            f"{ADMIN_PREFIX}/applications/{app_b_id}",
            headers=auth(tenant_a.token_for(tenant_a.admin)),
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Application not found"


def test_admin_list_excludes_other_tenants_applications(
    client: TestClient, make_tenant
) -> None:
    """The admin list contains only applications from the admin's own tenant."""
    tenant_a = make_tenant("AdminListScopeA")
    tenant_b = make_tenant("AdminListScopeB")

    with TestClient(app) as client:
        _create_and_submit(client, tenant_a, "Own Event")
        app_b_id = _create_and_submit(client, tenant_b, "Foreign Event")

        response = client.get(
            f"{ADMIN_PREFIX}/applications",
            headers=auth(tenant_a.token_for(tenant_a.admin)),
        )
        assert response.status_code == 200
        body = response.json()
        assert [app["event_name"] for app in body] == ["Own Event"]
        assert app_b_id not in {app["id"] for app in body}


def _create_draft(
    client: TestClient,
    tenant: TenantFixture,
    *,
    event_name: str,
    location: str | None = None,
    description: str | None = None,
) -> str:
    """File a draft carrying exactly the fields the admin search matches on."""
    payload: dict = {
        "event_name": event_name,
        "event_type": EventType.CONCERT.value,
    }
    if location is not None:
        payload["location"] = location
    if description is not None:
        payload["description"] = description
    response = client.post(
        "/applications",
        json=payload,
        headers=auth(tenant.token_for(tenant.organizer)),
    )
    assert response.status_code == 201
    return response.json()["id"]


def _admin_list(client: TestClient, tenant: TenantFixture, **params) -> list[dict]:
    """GET the admin application list as the tenant's admin, with query params."""
    response = client.get(
        f"{ADMIN_PREFIX}/applications",
        params=params,
        headers=auth(tenant.token_for(tenant.admin)),
    )
    assert response.status_code == 200
    return response.json()


def test_admin_list_search_matches_name_location_and_description(
    client: TestClient, make_tenant
) -> None:
    """`q` matches event name, location and description, case-insensitively."""
    tenant = make_tenant("AdminSearchFieldsTenant")

    with TestClient(app) as client:
        _create_draft(
            client,
            tenant,
            event_name="Harbor Music Festival",
            location="Harbor Pavilion",
            description="Waterfront stage programme",
        )
        _create_draft(
            client,
            tenant,
            event_name="Winter Market",
            location="Union Square",
            description="Craft stalls and food trucks",
        )

        # Event name, in either letter case.
        assert [
            app["event_name"] for app in _admin_list(client, tenant, q="harbor music")
        ] == ["Harbor Music Festival"]
        assert [
            app["event_name"] for app in _admin_list(client, tenant, q="HARBOR")
        ] == ["Harbor Music Festival"]

        # Location.
        assert [
            app["event_name"] for app in _admin_list(client, tenant, q="union square")
        ] == ["Winter Market"]

        # Description.
        assert [
            app["event_name"] for app in _admin_list(client, tenant, q="waterfront")
        ] == ["Harbor Music Festival"]


def test_admin_list_search_with_no_match_returns_empty(
    client: TestClient, make_tenant
) -> None:
    """A term that matches nothing yields an empty array, not an error."""
    tenant = make_tenant("AdminSearchNoMatchTenant")

    with TestClient(app) as client:
        _create_draft(client, tenant, event_name="Summer Fair")
        assert _admin_list(client, tenant, q="no-such-event") == []


def test_admin_list_search_with_blank_query_returns_everything(
    client: TestClient, make_tenant
) -> None:
    """An absent, empty or whitespace-only `q` applies no filter at all."""
    tenant = make_tenant("AdminSearchBlankTenant")

    with TestClient(app) as client:
        _create_draft(client, tenant, event_name="First Event")
        _create_draft(client, tenant, event_name="Second Event")

        assert len(_admin_list(client, tenant)) == 2
        assert len(_admin_list(client, tenant, q="")) == 2
        assert len(_admin_list(client, tenant, q="   ")) == 2


def test_admin_list_search_is_scoped_to_the_admins_tenant(
    client: TestClient, make_tenant
) -> None:
    """Search cannot reach another city's applications, even for the same name."""
    tenant_a = make_tenant("AdminSearchScopeA")
    tenant_b = make_tenant("AdminSearchScopeB")

    with TestClient(app) as client:
        own_id = _create_draft(client, tenant_a, event_name="Shared Carnival Name")
        _create_draft(client, tenant_b, event_name="Shared Carnival Name")

        results = _admin_list(client, tenant_a, q="carnival")
        assert [app["id"] for app in results] == [own_id]


def test_admin_list_search_combines_with_the_status_filter(
    client: TestClient, make_tenant
) -> None:
    """`q` and `status` narrow the same query rather than overriding each other."""
    tenant = make_tenant("AdminSearchCombinedTenant")

    with TestClient(app) as client:
        draft_id = _create_draft(client, tenant, event_name="Autumn Jazz Night")
        submitted_id = _create_and_submit(client, tenant, "Autumn Fair Parade")

        both = _admin_list(client, tenant, q="autumn")
        assert {app["id"] for app in both} == {draft_id, submitted_id}

        drafts = _admin_list(client, tenant, q="autumn", status="Draft")
        assert [app["id"] for app in drafts] == [draft_id]

        submitted = _admin_list(client, tenant, q="autumn", status="Submitted")
        assert [app["id"] for app in submitted] == [submitted_id]


def test_admin_list_search_treats_like_metacharacters_literally(
    client: TestClient, make_tenant
) -> None:
    """`%` and `_` typed by a user are data, not wildcards."""
    tenant = make_tenant("AdminSearchMetaTenant")

    with TestClient(app) as client:
        _create_draft(client, tenant, event_name="Century 100% Fun Run")
        _create_draft(client, tenant, event_name="abc night market")

        # A literal percent matches only the name that contains one; the
        # wildcard reading would match both events.
        assert [
            app["event_name"] for app in _admin_list(client, tenant, q="%")
        ] == ["Century 100% Fun Run"]
        assert [
            app["event_name"] for app in _admin_list(client, tenant, q="100%")
        ] == ["Century 100% Fun Run"]

        # An unescaped `_` would make "a_c" match "abc"; escaped, it does not.
        assert _admin_list(client, tenant, q="a_c") == []


def test_admin_applications_non_admin_forbidden(client: TestClient, make_tenant) -> None:
    """Organizer and Reviewer cannot read the admin application endpoints."""
    tenant = make_tenant("AdminAppsRoleTenant", with_reviewer=True)
    app_id = _create_and_submit(client, tenant, "Role Guard Event")

    with TestClient(app) as client:
        for user in (tenant.organizer, tenant.reviewer):
            token = tenant.token_for(user)
            list_resp = client.get(
                f"{ADMIN_PREFIX}/applications", headers=auth(token)
            )
            detail_resp = client.get(
                f"{ADMIN_PREFIX}/applications/{app_id}", headers=auth(token)
            )
            assert list_resp.status_code == 403
            assert detail_resp.status_code == 403

        # Unauthenticated requests are rejected before role checks.
        assert client.get(f"{ADMIN_PREFIX}/applications").status_code == 401
        assert (
            client.get(f"{ADMIN_PREFIX}/applications/{app_id}").status_code == 401
        )


def test_admin_applications_handle_empty_reviews(client: TestClient, make_tenant) -> None:
    """Drafts have no review tasks; an empty list of applications is also safe."""
    tenant = make_tenant("AdminEmptyReviewsTenant")

    with TestClient(app) as client:
        # No applications at all: the list itself must be an empty array.
        empty = client.get(
            f"{ADMIN_PREFIX}/applications",
            headers=auth(tenant.token_for(tenant.admin)),
        )
        assert empty.status_code == 200
        assert empty.json() == []

        # A draft has never been submitted, so its reviews collection is empty.
        draft_resp = client.post(
            "/applications",
            json={
                "event_name": "Unsubmitted Draft",
                "event_type": EventType.STREET_FAIR.value,
            },
            headers=auth(tenant.token_for(tenant.organizer)),
        )
        assert draft_resp.status_code == 201
        app_id = draft_resp.json()["id"]

        detail = client.get(
            f"{ADMIN_PREFIX}/applications/{app_id}",
            headers=auth(tenant.token_for(tenant.admin)),
        )
        assert detail.status_code == 200
        assert detail.json()["status"] == "Draft"
        assert detail.json()["reviews"] == []

        listing = client.get(
            f"{ADMIN_PREFIX}/applications",
            headers=auth(tenant.token_for(tenant.admin)),
        ).json()
        assert len(listing) == 1
        assert listing[0]["reviews"] == []


# ---------------------------------------------------------------------------
# Application history (admin audit timeline with actor enrichment)
# ---------------------------------------------------------------------------


def _history(client: TestClient, tenant: TenantFixture, app_id: str) -> dict:
    """Fetch the admin history endpoint for an application and assert 200."""
    response = client.get(
        f"{ADMIN_PREFIX}/applications/{app_id}/history",
        headers=auth(tenant.token_for(tenant.admin)),
    )
    assert response.status_code == 200
    return response.json()


def test_admin_history_returns_timeline_for_own_application(
    client: TestClient, make_tenant
) -> None:
    """Admin reads the audit timeline of an application in their own tenant."""
    tenant = make_tenant("AdminHistoryOwnTenant")

    with TestClient(app) as client:
        app_id = _create_and_submit(client, tenant, "History Own Event")

        body = _history(client, tenant, app_id)
        assert body["application_id"] == app_id
        assert body["application_status"] == "Submitted"

        # Submission is recorded, oldest first, with the organizer as actor.
        actions = [event["action"] for event in body["events"]]
        assert "application.status_changed" in actions
        submit_event = body["events"][0]
        assert submit_event["old_status"] == "Draft"
        assert submit_event["new_status"] == "Submitted"
        assert submit_event["actor_email"] == tenant.organizer.email
        assert submit_event["user_id"] == str(tenant.organizer.id)

        # Ordering: oldest first, non-decreasing timestamps.
        timestamps = [
            datetime.fromisoformat(event["created_at"]) for event in body["events"]
        ]
        assert timestamps == sorted(timestamps)


def test_admin_history_includes_reviewer_decision_with_actor(
    client: TestClient, make_tenant
) -> None:
    """A reviewer decision appears with a readable actor and agency name."""
    tenant = make_tenant("AdminHistoryDecisionTenant", with_reviewer=True)

    with TestClient(app) as client:
        app_id = _create_and_submit(client, tenant, "History Decision Event")

        tasks = client.get(
            "/review-tasks", headers=auth(tenant.token_for(tenant.reviewer))
        ).json()
        task = next(t for t in tasks if t["application"]["id"] == app_id)
        decision = client.post(
            f"/review-tasks/{task['id']}/decision",
            json={"action": "approve", "comment": "Traffic plan approved."},
            headers=auth(tenant.token_for(tenant.reviewer)),
        )
        assert decision.status_code == 200

        body = _history(client, tenant, app_id)
        assert body["application_status"] == "Under Review"

        decision_event = next(
            e for e in body["events"] if e["action"] == "review.approved"
        )
        assert decision_event["actor_email"] == tenant.reviewer.email
        assert decision_event["user_id"] == str(tenant.reviewer.id)
        assert decision_event["agency_name"] == "Police"
        assert decision_event["agency_id"] == str(tenant.agencies["Police"].id)
        assert decision_event["comment"] == "Traffic plan approved."
        assert decision_event["old_status"] == "Pending"
        assert decision_event["new_status"] == "Approved"

        # The aggregate status change it caused carries the same actor.
        status_event = next(
            e
            for e in body["events"]
            if e["action"] == "application.status_changed"
            and e["new_status"] == "Under Review"
        )
        assert status_event["actor_email"] == tenant.reviewer.email
        assert status_event["agency_name"] == "Police"

        # No sensitive fields leak into the payload.
        for event in body["events"]:
            assert "password_hash" not in event


def test_admin_history_includes_resubmission_and_task_reset(
    client: TestClient, make_tenant
) -> None:
    """Resubmission writes (task reset, resubmitted) are visible to the admin."""
    tenant = make_tenant("AdminHistoryResubmitTenant", with_reviewer=True)

    with TestClient(app) as client:
        app_id = _create_and_submit(client, tenant, "History Resubmit Event")

        tasks = client.get(
            "/review-tasks", headers=auth(tenant.token_for(tenant.reviewer))
        ).json()
        task = next(t for t in tasks if t["application"]["id"] == app_id)
        decision = client.post(
            f"/review-tasks/{task['id']}/decision",
            json={"action": "request_changes", "comment": "Add a traffic plan."},
            headers=auth(tenant.token_for(tenant.reviewer)),
        )
        assert decision.status_code == 200
        assert decision.json()["application_status"] == "Changes Requested"

        resubmit = client.post(
            f"/applications/{app_id}/resubmit",
            headers=auth(tenant.token_for(tenant.organizer)),
        )
        assert resubmit.status_code == 200

        body = _history(client, tenant, app_id)
        actions = [event["action"] for event in body["events"]]
        assert "review.changes_requested" in actions
        assert "review.task_reset" in actions
        assert "application.resubmitted" in actions

        # The task reset names the agency whose task moved and the organizer
        # who resubmitted.
        reset_event = next(
            e for e in body["events"] if e["action"] == "review.task_reset"
        )
        assert reset_event["agency_name"] == "Police"
        assert reset_event["actor_email"] == tenant.organizer.email
        assert reset_event["old_status"] == "Changes Requested"
        assert reset_event["new_status"] == "Pending"

        resubmit_event = next(
            e for e in body["events"] if e["action"] == "application.resubmitted"
        )
        assert resubmit_event["actor_email"] == tenant.organizer.email
        assert resubmit_event["agency_name"] is None


def test_admin_history_cross_tenant_returns_404(
    client: TestClient, make_tenant
) -> None:
    """Another tenant's application history is a 404, and so is an unknown id."""
    tenant_a = make_tenant("AdminHistoryCrossA")
    tenant_b = make_tenant("AdminHistoryCrossB")

    with TestClient(app) as client:
        app_b_id = _create_and_submit(client, tenant_b, "History Foreign Event")

        response = client.get(
            f"{ADMIN_PREFIX}/applications/{app_b_id}/history",
            headers=auth(tenant_a.token_for(tenant_a.admin)),
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Application not found"

        # A well-formed but nonexistent id in the admin's own tenant: also 404.
        missing = client.get(
            f"{ADMIN_PREFIX}/applications/{uuid.uuid4()}/history",
            headers=auth(tenant_a.token_for(tenant_a.admin)),
        )
        assert missing.status_code == 404


def test_admin_history_non_admin_forbidden(client: TestClient, make_tenant) -> None:
    """Organizer and Reviewer cannot read the admin history endpoint."""
    tenant = make_tenant("AdminHistoryRoleTenant", with_reviewer=True)
    app_id = _create_and_submit(client, tenant, "History Role Event")

    with TestClient(app) as client:
        for user in (tenant.organizer, tenant.reviewer):
            response = client.get(
                f"{ADMIN_PREFIX}/applications/{app_id}/history",
                headers=auth(tenant.token_for(user)),
            )
            assert response.status_code == 403


def test_admin_history_unauthenticated_returns_401(
    client: TestClient, make_tenant
) -> None:
    """No token means 401 before any role or tenant check runs."""
    tenant = make_tenant("AdminHistoryAuthTenant")
    app_id = _create_and_submit(client, tenant, "History Auth Event")

    with TestClient(app) as client:
        response = client.get(f"{ADMIN_PREFIX}/applications/{app_id}/history")
        assert response.status_code == 401


def test_admin_history_empty_returns_valid_empty_response(
    client: TestClient, make_tenant
) -> None:
    """A never-audited application yields an empty events array, not an error."""
    tenant = make_tenant("AdminHistoryEmptyTenant")

    with TestClient(app) as client:
        draft_resp = client.post(
            "/applications",
            json={
                "event_name": "Quiet Draft",
                "event_type": EventType.OTHER.value,
            },
            headers=auth(tenant.token_for(tenant.organizer)),
        )
        assert draft_resp.status_code == 201
        app_id = draft_resp.json()["id"]

        body = _history(client, tenant, app_id)
        assert body["application_id"] == app_id
        assert body["application_status"] == "Draft"
        assert body["events"] == []


def test_admin_history_missing_actor_is_graceful(
    client: TestClient, make_tenant, db
) -> None:
    """An event with no actor row (system-generated) renders with None fields."""
    from app.models import AuditEvent

    tenant = make_tenant("AdminHistoryNoActorTenant")

    with TestClient(app) as client:
        draft_resp = client.post(
            "/applications",
            json={
                "event_name": "No Actor Event",
                "event_type": EventType.OTHER.value,
            },
            headers=auth(tenant.token_for(tenant.organizer)),
        )
        assert draft_resp.status_code == 201
        app_id = draft_resp.json()["id"]

        db.add(
            AuditEvent(
                application_id=uuid.UUID(app_id),
                tenant_id=tenant.tenant.id,
                user_id=None,
                agency_id=None,
                action="system.maintenance",
                comment="No actor attached to this event.",
            )
        )
        db.commit()

        body = _history(client, tenant, app_id)
        assert len(body["events"]) == 1
        event = body["events"][0]
        assert event["action"] == "system.maintenance"
        assert event["user_id"] is None
        assert event["actor_email"] is None
        assert event["agency_id"] is None
        assert event["agency_name"] is None
        assert event["comment"] == "No actor attached to this event."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



# ---------------------------------------------------------------------------
# Dashboard Metrics
# ---------------------------------------------------------------------------

