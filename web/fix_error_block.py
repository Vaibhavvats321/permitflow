with open(r'C:\Projects\PermitFlow\web\src\app\(admin)\admin-dashboard\dashboard-content.tsx') as f:
    lines = f.readlines()

# Find the line with '}, [data]);' and insert error block after it
new_lines = []
inserted = False
for line in lines:
    new_lines.append(line)
    if '}, [data]);' in line and not any('if (error)' in l for l in lines[max(0, lines.index(line)-5):lines.index(line)]):
        # Insert error block after this line
        new_lines.extend([
            '\n',
            '  if (error) {\n',
            '    return (\n',
            '      <>\n',
            '        <PageHeader\n',
            '          title="Admin dashboard"\n',
            '          description="City-wide permit application metrics."\n',
            '        />\n',
            '        <PageBody>\n',
            '          <ErrorState error={error} onRetry={reload} />\n',
            '        </PageBody>\n',
            '      </>\n',
            '    );\n',
            '  }\n',
            '\n',
        ])
        print('Inserted error block')

with open(r'C:\Projects\PermitFlow\web\src\app\(admin)\admin-dashboard\dashboard-content.tsx', 'w') as f:
    f.write(''.join(new_lines))
print('Added error block')