with open('src/components/layout/sidebar.tsx') as f:
    content = f.read()
import re
match = re.search(r'ADMIN_NAV.*?href: "(.*?)"', content, re.DOTALL)
if match:
    print(f'Admin dashboard href: {match.group(1)}')
else:
    print('ADMIN_NAV not found')