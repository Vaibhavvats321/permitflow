import re

with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'r') as f:
    content = f.read()

old = '''def test_dashboard_approved_count(client: TestClient, make_tenant) -> None:
    """Approved count is correct."""
    tenant = make_tenant("DashboardApprovedTenant", with_reviewer=True)
    admin_token = tenant.token_for(tenant.admin)
    organizer_token = tenant.token_for(tenant.organizer)
    reviewer_token = tenant.token_for(tenant.reviewer)

    with TestClient(app) as client:
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)
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
            headers=auth(tenant.token_for(tenant.organizer)),
        )
        assert draft_resp.status_code == 201
        app_id = draft_resp.json()["id"]

        # Submit
        submit_resp = client.post(f"/applications/{app_id}/submit", headers=auth(tenant.token_for(tenant.organizer)))
        assert submit_resp.status_code == 200

        # Approve all reviewers
        tasks = client.get("/review-tasks", headers=auth(tenant.token_for(tenant.reviewer))).json()
        for task in tasks:
            client.post(
                f"/review-tasks/{task['id']}/decision",
                json={"action": "approve", "comment": "Approved"},
                headers=auth(tenant.token_for(tenant.reviewer)),
            )

        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(tenant.token_for(tenant.admin)))
        assert response.status_code == 200
        body = response.json()
        assert body["approved_applications"] == 1
        assert body["rejected_applications"] == 0'''

new = '''def test_dashboard_approved_count(client: TestClient, make_tenant) -> None:
    """Approved count is correct."""
    tenant = make_tenant("DashboardApprovedTenant", with_reviewer=True)
    admin_token = tenant.token_for(tenant.admin)
    organizer_token = tenant.token_for(tenant.organizer)
    reviewer_token = tenant.token_for(tenant.reviewer)

    with TestClient(app) as client:
        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
        END = START + timedelta(hours=6)
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

        # Submit - but first remove Health from routing so only Police reviews
        with TestClient(app) as client:
            # Remove Health from Marathon routing
            health_id = tenant.agencies["Health"].id
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
            assert body["rejected_applications"] == 0'''

content = content.replace(old, new)

with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'w') as f:
    f.write(content)
print('Updated test_dashboard_approved_count')