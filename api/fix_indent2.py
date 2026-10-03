with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'r') as f:
    lines = f.readlines()

# Fix line 1723 (index 1722) - the assert is over-indented
# Line 1723 (index 1722) should be at the same indentation as line 1720
# Current: lines[1722] = '            assert delete_resp.status_code == 204\n'
# Should be: '        assert delete_resp.status_code == 204\n'

lines[1722] = '        assert delete_resp.status_code == 204\n'

with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'w') as f:
    f.writelines(lines)
print('Fixed indentation')