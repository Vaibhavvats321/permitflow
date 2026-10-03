with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'r') as f:
    lines = f.readlines()

# Fix the timestamp test section (lines 1725-1761)
# Remove the over-indented comment line 1725
# Fix the duplicate for loop at line 1750
# Remove duplicate response line 1757

new_lines = []
skip_next = False
for i, line in enumerate(lines):
    line_num = i + 1
    
    # Skip the over-indented comment at line 1725 (index 1724)
    if i == 1724:
        continue
    
    # Fix line 1750 (duplicate for loop) - index 1749
    if i == 1749 and 'for task in tasks:' in lines[i]:
        # Skip the duplicate
        continue
    
    # Remove duplicate response line at line 1757 (index 1756)
    if i == 1756 and 'response = client.get(f"{ADMIN_PREFIX}/dashboard"' in lines[i]:
        continue
    
    new_lines.append(lines[i])

with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'w') as f:
    f.writelines(new_lines)
print('Fixed duplicate lines')