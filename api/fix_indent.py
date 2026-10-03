with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'r') as f:
    content = f.read()

# Fix indentation issues in the timestamp test
content = content.replace(
    '        delete_resp = client.delete(\n'
    '                f"{ADMIN_PREFIX}/routing/Marathon/{health_id}", headers=auth(admin_token)\n'
    '            )\n',
    '        delete_resp = client.delete(\n'
    '            f"{ADMIN_PREFIX}/routing/Marathon/{health_id}", headers=auth(admin_token)\n'
    '        )\n'
)

with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'w') as f:
    f.write(content)
print('Fixed indentation')