with open(r'C:\Projects\PermitFlow\web\src\app\(admin)\admin-dashboard\dashboard-content.tsx') as f:
    lines = f.readlines()

# Remove the erroneous fragment wrapper around the error block (lines 136-146)
# Keep lines 0-134 (useMemo closing), then jump to line 147 (if (isLoading))
# The error block should be directly after the useMemo, without the extra fragment

# Lines to keep: 0-134 (up to "  }, [data]);")
# Skip lines 135-146 (the erroneous fragment wrapper)
# Resume from line 147 (if (isLoading) {)

new_lines = lines[:135] + lines[147:]

with open(r'C:\Projects\PermitFlow\web\src\app\(admin)\admin-dashboard\dashboard-content.tsx', 'w') as f:
    f.write(''.join(new_lines))

print('Fixed dashboard-content.tsx')