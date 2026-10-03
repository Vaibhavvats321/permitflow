import re

with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'r') as f:
    content = f.read()

# Find the function
pattern = r'(def test_dashboard_avg_days_uses_submission_and_decision_timestamps\(client: TestClient, make_tenant\) -> None:.*?)(?=\ndef test_)'

match = re.search(pattern, content, re.DOTALL)
if match:
    # Replacement function body
    new_func = '''def test_dashboard_avg_days_uses_submission_and_decision_timestamps(client: TestClient, make_tenant) -> None:
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

def test_dashboard_zero_completed_applications_no_division_error(client: TestClient, make_tenant) -> None:'''

    # Replace the old function
    content = content.replace(match.group(1), match.group(1)[:match.group(1).rfind('def test_dashboard_zero_completed_applications_no_division_error') - match.start(1)] + match.group(1)[match.group(1).rfind('def test_dashboard_zero_completed_applications_no_division_error'):match.start(1) + len(match.group(1))])
    # Actually simpler: just replace the entire match
    content = content[:match.start()] + new_func + content[match.end():]

with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'w') as f:
    f.write(content)
print('Fixed')