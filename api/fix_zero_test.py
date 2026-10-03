with open(r'C:\Projects\PermitFlow\api\tests\test_admin_recovered.py', 'r') as f:
    lines = f.read().split('\n')

# Fix the corrupted test function at line 1763 (index 1762)
# Replace lines 1763-1766 with a proper function body
# Find the function start
for i, line in enumerate(lines):
    if 'def test_dashboard_zero_completed_applications_no_division_error' in line:
        start = i
        break

# Find the end of this function (next function definition)
for i in range(start + 1, len(lines)):
    if lines[i].startswith('def test_'):
        end = i
        break
else:
    end = len(lines)

print(f'Function at lines {start+1} to {end}')
for i in range(start, min(end, start + 15)):
    print(f'{i+1}: {lines[i]}')

# Replace the corrupted function body
# The function should test that dashboard handles zero completed applications
new_body = [
    'def test_dashboard_zero_completed_applications_no_division_error(client: TestClient, make_tenant) -> None:',
    '    """Zero completed applications returns a safe value without division errors."""',
    '    tenant = make_tenant("DashboardZeroCompletedTenant")',
    '    admin_token = tenant.token_for(tenant.admin)',
    '',
    '    with TestClient(app) as client:',
    '        # No applications at all',
    '        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(admin_token))',
    '        assert response.status_code == 200',
    '        body = response.json()',
    '        assert body["average_days_to_decision"] is None',
    '',
    '        # Only draft applications',
    '        START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)',
    '        END = START + timedelta(hours=6)',
    '        client.post(',
    '            "/applications",',
    '            json={',
    '                "event_name": "Draft Only",',
    '                "event_type": EventType.MARATHON.value,',
    '                "start_date": START.isoformat(),',
    '                "end_date": END.isoformat(),',
    '                "location": "Test",',
    '                "expected_attendance": 1000,',
    '                "description": "Test",',
    '            },',
    '            headers=auth(tenant.token_for(tenant.organizer)),',
    '        )',
    '',
    '        response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(admin_token))',
    '        body = response.json()',
    '        # No completed applications, average should be None',
    '        assert body["average_days_to_decision"] is None',
    '',
]

# Replace the corrupted section
new_lines = lines[:start] + new_body + lines[end:]

with open(r'C:\Projects\PermitFlow\api\tests\test_admin_recovered.py', 'w') as f:
    f.write('\n'.join(new_lines))

print('Fixed test_dashboard_zero_completed_applications_no_division_error')
"