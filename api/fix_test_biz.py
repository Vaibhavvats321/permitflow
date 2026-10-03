with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py') as f:
    content = f.read()

old = """# Verify existing review tasks are NOT deleted/modified
        review_tasks = client.get(
            "/review-tasks", headers=auth(tenant.token_for(tenant.reviewer))
        )
        tasks = review_tasks.json()
        custom_tasks = [t for t in tasks if t["agency_id"] == agency_id]
        # The existing review task for CustomBiz should still exist
        assert len(custom_tasks) > 0"""

new = """# Verify existing review tasks are NOT deleted/modified
        # Use the custom reviewer's token to see their tasks
        review_tasks = client.get(
            "/review-tasks", headers=auth(custom_reviewer_token)
        )
        tasks = review_tasks.json()
        custom_tasks = [t for t in tasks if t["agency_id"] == agency_id]
        # The existing review task for CustomBiz should still exist
        assert len(custom_tasks) > 0"""

content = content.replace(old, new)

with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'w') as f:
    f.write(content)
print('Fixed test')