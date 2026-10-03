with open(r'tests\test_admin.py', 'r') as f:
    content = f.read()

# Fix 1: Remove nested TestClient in avg test
content = content.replace(
    'with TestClient(app) as client:\n        # Remove Health from Marathon routing so only Police reviews\n        admin_token = tenant.token_for(tenant.admin)\n        health_id = tenant.agencies["Health"].id\n        with TestClient(app) as client:\n            delete_resp = client.delete(',
    'with TestClient(app) as client:\n        # Remove Health from Marathon routing so only Police reviews\n        admin_token = tenant.token_for(tenant.admin)\n        health_id = tenant.agencies["Health"].id\n        delete_resp = client.delete('
)

content = content.replace(
    '            assert delete_resp.status_code == 204\n\n            # Create and approve an application\n            START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)\n            END = START + timedelta(hours=6)\n            draft_resp = client.post(\n',
    '            assert delete_resp.status_code == 204\n\n            # Create and approve an application\n            START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)\n            END = START + timedelta(hours=6)\n            draft_resp = client.post(\n'
)

content = content.replace(
    '            )]\n        assert draft_resp.status_code == 201\n        app_id = draft_resp.json()["id"]\n\n        # Submit\n        submit_resp = client.post(f"/applications/{app_id}/submit", headers=auth(organizer_token))\n        assert submit_resp.status_code == 200\n\n        # Approve all\n        tasks = client.get("/review-tasks", headers=auth(reviewer_token)).json()\n        for task in tasks:\n            client.post(\n                f"/review-tasks/{task[\'id\']}/decision",\n                json={"action": "approve", "comment": "Approved"},\n                headers=auth(reviewer_token),\n            )\n\n        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(admin_token))\n        body = response.json()\n        # Should have a non-negative average (could be 0 if same-day)\n        assert body["average_days_to_decision"] is not None\n        assert body["average_days_to_decision"] >= 0',
    '            )]\n        assert draft_resp.status_code == 201\n        app_id = draft_resp.json()["id"]\n\n        # Submit\n        submit_resp = client.post(f"/applications/{app_id}/submit", headers=auth(organizer_token))\n        assert submit_resp.status_code == 200\n\n        # Approve all\n        tasks = client.get("/review-tasks", headers=auth(reviewer_token)).json()\n        for task in tasks:\n            client.post(\n                f"/review-tasks/{task[\'id\']}/decision",\n                json={"action": "approve", "comment": "Approved"},\n                headers=auth(reviewer_token),\n            )\n\n        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(admin_token))\n        body = response.json()\n        # Should have a non-negative average (could be 0 if same-day)\n        assert body["average_days_to_decision"] is not None\n        assert body["average_days_to_decision"] >= 0'
)

with open('tests/test_admin.py', 'w') as f:
    f.write(content)
print('Fixed avg test')