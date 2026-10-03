with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py.bak') as f:
    lines = f.read().split('\n')

# Take first copy (1821 lines)
first_copy = lines[:1821]

# Fix corruption at line 1763 (0-indexed: 1762)
for i, line in enumerate(first_copy):
    if 'test_dashboard_zero_completed_applications_no_division_error' in line and 'ected_keys' in line:
        first_copy[i] = 'def test_dashboard_zero_completed_applications_no_division_error(client: TestClient, make_tenant) -> None:'
        print(f'Fixed line {i+1}')
        break

# Write recovered file
with open(r'C:\Projects\PermitFlow\api\tests\test_admin_recovered.py', 'w') as f:
    f.write('\n'.join(first_copy))

print('Written test_admin_recovered.py')
print(f'Lines: {len(open(r"C:\\Projects\\PermitFlow\\api\\tests\\test_admin_recovered.py").read().split(chr(10)))}')