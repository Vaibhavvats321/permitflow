with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'r') as f:
    lines = f.readlines()

# Fix the timestamp test section - lines 1725-1761 need proper indentation
# Line 1725 (index 1724) should be 8 spaces, not 12
# Line 1726 (END = ...) should be 12 spaces
# etc.

# Fix line 1725 (index 1724): change from 12 spaces to 8 spaces
if lines[1724].startswith('            '):
    lines[1724] = lines[1724].replace('            ', '        ', 1)

# Fix line 1726 (index 1725): END = ...
if lines[1725].startswith('            '):
    lines[1725] = lines[1725].replace('            ', '        ', 1)

# Fix line 1727 (index 1726): draft_resp = client.post(
if lines[1726].startswith('            '):
    lines[1726] = lines[1726].replace('            ', '        ', 1)

# Fix line 1728 (index 1727): "/applications",
if lines[1727].startswith('                '):
    lines[1727] = lines[1727].replace('                ', '            ', 1)

# Fix line 1729 (index 1728): json={
if lines[1728].startswith('                '):
    lines[1728] = lines[1728].replace('                ', '            ', 1)

# Fix line 1729 (index 1729): "event_name": ...
if lines[1729].startswith('                    '):
    lines[1729] = lines[1729].replace('                    ', '            ', 1)

# Fix line 1730 (index 1730): "event_type": ...
if lines[1730].startswith('                    '):
    lines[1730] = lines[1730].replace('                    ', '            ', 1)

# Fix line 1731 (index 1731): "start_date": ...
if lines[1731].startswith('                    '):
    lines[1731] = lines[1731].replace('                    ', '            ', 1)

# Fix line 1732 (index 1732): "end_date": ...
if lines[1732].startswith('                    '):
    lines[1732] = lines[1732].replace('                    ', '            ', 1)

# Fix line 1733 (index 1733): "location": ...
if lines[1733].startswith('                    '):
    lines[1733] = lines[1733].replace('                    ', '            ', 1)

# Fix line 1734 (index 1734): "expected_attendance": ...
if lines[1734].startswith('                    '):
    lines[1734] = lines[1734].replace('                    ', '            ', 1)

# Fix line 1735 (index 1735): "description": ...
if lines[1735].startswith('                    '):
    lines[1735] = lines[1735].replace('                    ', '            ', 1)

# Fix line 1736 (index 1736): },
if lines[1736].startswith('                    '):
    lines[1736] = lines[1736].replace('                    ', '            ', 1)

# Fix line 1737 (index 1737): headers=...
if lines[1737].startswith('                    '):
    lines[1737] = lines[1737].replace('                    ', '            ', 1)

# Fix line 1738 (index 1738): )
if lines[1738].startswith('            '):
    lines[1738] = lines[1738].replace('            ', '        ', 1)

# Fix line 1739 (index 1739): assert draft_resp...
if lines[1739].startswith('            '):
    lines[1739] = lines[1739].replace('            ', '        ', 1)

# Fix line 1740 (index 1740): app_id = ...
if lines[1740].startswith('            '):
    lines[1740] = lines[1740].replace('            ', '        ', 1)

# Fix line 1742 (index 1742): (blank line)
# Already correct

# Fix line 1744 (index 1743): submit_resp = ...
if lines[1743].startswith('            '):
    lines[1743] = lines[1743].replace('            ', '        ', 1)

# Fix line 1744 (index 1744): assert submit...
if lines[1744].startswith('            '):
    lines[1744] = lines[1744].replace('            ', '        ', 1)

# Fix line 1746 (index 1746): (blank)
# Already correct

# Fix line 1747 (index 1747): # Approve
if lines[1747].startswith('            '):
    lines[1747] = lines[1747].replace('            ', '        ', 1)

# Fix line 1750 (index 1749): duplicate for loop - remove second one
if lines[1749].strip() == 'for task in tasks:' and lines[1748].strip() == 'for task in tasks:':
    # Remove the second occurrence
    pass  # handled by removing the second one

# Fix line 1751 (index 1750): for task in tasks:
if lines[1749].startswith('                '):
    lines[1749] = lines[1749].replace('                ', '            ', 1)

# Fix line 1751 (index 1750): f"/review-tasks/...
if lines[1750].startswith('                    '):
    lines[1750] = lines[1750].replace('                    ', '            ', 1)

# Fix line 1752 (index 1751): json=...
if lines[1751].startswith('                    '):
    lines[1751] = lines[1751].replace('                    ', '            ', 1)

# Fix line 1753 (index 1752): headers=...
if lines[1752].startswith('                    '):
    lines[1752] = lines[1752].replace('                    ', '            ', 1)

# Fix line 1753 (index 1753): )
if lines[1753].startswith('                '):
    lines[1753] = lines[1753].replace('                ', '            ', 1)

# Fix line 1755 (index 1754): (blank)
# Already correct

# Fix line 1756 (index 1754): duplicate response line - remove
if lines[1754].startswith('            response = client.get'):
    # Check if it's a duplicate
    if lines[1753].strip().startswith('response = client.get'):
        # Remove this line
        pass  # will be handled by removing the line

with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'r') as f:
    content = f.read()

# Better approach: rewrite the entire problematic section
# Find the test_dashboard_avg_days_uses_submission_and_decision_timestamps function
# and fix its indentation

# Read the file as a string and do a more targeted replacement
content = open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'r').read()

# The issue is in the test_dashboard_avg_days_uses_submission_and_decision_timestamps function
# The block from "START = datetime..." to the end of the function has wrong indentation

# Let's find the function and fix it properly
import re

# Pattern to match the problematic function
pattern = r'(def test_dashboard_avg_days_uses_submission_and_decision_timestamps\(client: TestClient, make_tenant\) -> None:.*?)(?=\ndef test_)'

match = re.search(pattern, content, re.DOTALL)
if match:
    func_content = match.group(1)
    # Fix indentation in the function body
    # Replace 12-space indent with 8-space indent for the body
    fixed = re.sub(r'^            (START|END|draft_resp|submit_resp|tasks|response|body|assert|#)', r'        \1', func_content, flags=re.MULTILINE)
    # Also fix the comment line
    fixed = re.sub(r'^            # (Create|Submit|Approve)', r'        # \1', fixed)
    # Fix the duplicate for loop
    fixed = re.sub(r'^            for task in tasks:\n            for task in tasks:', r'            for task in tasks:', fixed)
    # Fix duplicate response line
    fixed = re.sub(r'^            response = client\.get\(f"{ADMIN_PREFIX}/dashboard", headers=auth\(admin_token\)\)\n            response = client\.get\(f"{ADMIN_PREFIX}/dashboard", headers=auth\(admin_token\)\)', r'            response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(admin_token))', fixed)
    # Fix the blank line before assert
    fixed = re.sub(r'assert body\["average_days_to_decision"\]', r'        assert body["average_days_to_decision"]', fixed)
    fixed = re.sub(r'assert body\["average_days_to_decision"\] >= 0', r'        assert body["average_days_to_decision"] >= 0', fixed)
    
    content = content[:match.start()] + fixed + content[match.end():]

with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'w') as f:
    f.write(content)
print('Fixed')