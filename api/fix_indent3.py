with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'r') as f:
    lines = f.readlines()

# Fix the indentation for the timestamp test (lines 1716-1761)
# The block from line 1725-1761 should be at the same indentation as line 1716

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    line_num = i + 1
    
    # Fix the timestamp test block (lines 1725-1761 approximately)
    # The block starting at line 1725 has extra indentation
    if i == 1724:  # line 1725 (0-indexed 1724)
        # Skip the over-indented comment line
        i += 1
        continue
    elif i == 1725:  # line 1726
        # START = datetime... should be at 8 spaces (inside with block)
        lines[i] = '            START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)\n'
        i += 1
        continue
    elif i == 1726:  # line 1727
        lines[i] = '            END = START + timedelta(hours=6)\n'
        i += 1
        continue
    elif i == 1727:  # line 1728
        lines[i] = '            draft_resp = client.post(\n'
        i += 1
        continue
    elif i == 1728:  # line 1729
        lines[i] = '                "/applications",\n'
        i += 1
        continue
    elif i == 1729:  # line 1730
        lines[i] = '                json={\n'
        i += 1
        continue
    elif i == 1730:  # line 1731
        lines[i] = '                    "event_name": "Timestamp Test",\n'
        i += 1
        continue
    elif i == 1731:  # line 1732
        lines[i] = '                    "event_type": EventType.MARATHON.value,\n'
        i += 1
        continue
    elif i == 1732:  # line 1733
        lines[i] = '                    "start_date": START.isoformat(),\n'
        i += 1
        continue
    elif i == 1733:  # line 1734
        lines[i] = '                    "end_date": END.isoformat(),\n'
        i += 1
        continue
    elif i == 1734:  # line 1735
        lines[i] = '                    "location": "Test",\n'
        i += 1
        continue
    elif i == 1735:  # line 1736
        lines[i] = '                    "expected_attendance": 1000,\n'
        i += 1
        continue
    elif i == 1736:  # line 1737
        lines[i] = '                    "description": "Test",\n'
        i += 1
        continue
    elif i == 1737:  # line 1738
        lines[i] = '                },\n'
        i += 1
        continue
    elif i == 1738:  # line 1739
        lines[i] = '                headers=auth(organizer_token),\n'
        i += 1
        continue
    elif i == 1739:  # line 1740
        lines[i] = '            )\n'
        i += 1
        continue
    elif i == 1740:  # line 1741
        lines[i] = '            assert draft_resp.status_code == 201\n'
        i += 1
        continue
    elif i == 1741:  # line 1742
        lines[i] = '            app_id = draft_resp.json()["id"]\n'
        i += 1
        continue
    elif i == 1742:  # line 1743
        lines[i] = '\n'
        i += 1
        continue
    elif i == 1743:  # line 1744
        lines[i] = '            submit_resp = client.post(f"/applications/{app_id}/submit", headers=auth(organizer_token))\n'
        i += 1
        continue
    elif i == 1744:  # line 1745
        lines[i] = '            assert submit_resp.status_code == 200\n'
        i += 1
        continue
    elif i == 1745:  # line 1746
        lines[i] = '\n'
        i += 1
        continue
    elif i == 1746:  # line 1747
        lines[i] = '            # Approve\n'
        i += 1
        continue
    elif i == 1747:  # line 1748
        lines[i] = '            tasks = client.get("/review-tasks", headers=auth(reviewer_token)).json()\n'
        i += 1
        continue
    elif i == 1749:  # line 1750
        lines[i] = '            for task in tasks:\n'
        i += 1
        continue
    elif i == 1750:  # line 1750
        # This is the for loop line, already correct
        pass
    elif i == 1751:  # line 1751
        pass
    elif i == 1752:  # line 1752
        pass
    elif i == 1753:  # line 1753
        pass
    elif i == 1754:  # line 1754
        pass
    elif i == 1755:  # line 1755
        pass
    elif i == 1756:  # line 1756
        lines[i] = '\n'
        i += 1
        continue
    elif i == 1757:  # line 1757
        lines[i] = '            response = client.get(f"{ADMIN_PREFIX}/dashboard", headers=auth(admin_token))\n'
        i += 1
        continue
    elif i == 1758:  # line 1758
        lines[i] = '            body = response.json()\n'
        i += 1
        continue
    elif i == 1759:  # line 1759
        lines[i] = '            # The average should be computed from ReviewTask.updated_at - Application.created_at\n'
        i += 1
        continue
    elif i == 1760:  # line 1760
        lines[i] = '            # which should be >= 0 (same day or later)\n'
        i += 1
        continue
    elif i == 1761:  # line 1760
        pass
    elif i == 1761:  # line 1761
        lines[i] = '            assert body["average_days_to_decision"] >= 0\n'
        i += 1
        continue
    elif i == 1762:  # line 1762
        pass

    new_lines.append(lines[i])
    i += 1

with open(r'C:\Projects\PermitFlow\api\tests\test_admin.py', 'w') as f:
    f.writelines(lines)
print('Fixed indentation')