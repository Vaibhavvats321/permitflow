import re

with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'r') as f:
    content = f.read()

# Fix test_dashboard_avg_days_to_decision_calculated_from_completed
old = '''def test_dashboard_avg_days_to_decision_calculated_from_completed(client: TestClient, make_tenant) -> None:
    """Average days to decision is calculated only from completed applications."""
    tenant = make_tenant("DashboardAvgTenant", with_reviewer=True)
    admin_token = tenant.token_for(tenant.admin)
    organizer_token = tenant.token_for(tenant.organizer)
    reviewer_token = tenant.token_for(tenant.reviewer)

    with TestClient(app) as client:
        # Remove Health from Marathon routing so only Police reviews
        admin_token = tenant.token_for(tenant.admin)
        health_id = tenant.agencies["Health"].id
        with TestClient(app) as client:
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
            assert body["average_days_to_decision"] >= 0'''

new = '''def test_dashboard_avg_days_to_decision_calculated_from_completed(client: TestClient, make_tenant) -> None:
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
        assert body["average_days_to_decision"] >= 0'''

content = content.replace(old, new)

with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'w') as f:
    f.write(content)
print('Updated test_dashboard_avg_days_to_decision_calculated_from_completed')