import uuid
from datetime import UTC, datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.models import EventType, UserRole
import sqlalchemy as sa
from app.core.config import settings
from app.db.session import engine
from sqlalchemy.orm import Session
from app.core.security import create_access_token

# Create a tenant using the same logic as the fixture
factory = sa.orm.sessionmaker(bind=engine, autoflush=False)
db = factory()

try:
    from tests.conftest import TenantFixture, TEST_PASSWORD
    tenant = TenantFixture(db, 'DebugTenant2', with_reviewer=True)
    db.commit()
    
    print('Tenant:', tenant.tenant.id)
    print('Organizer:', tenant.organizer.id, tenant.organizer.email)
    print('Admin:', tenant.admin.id, tenant.admin.email)
    print('Reviewer:', tenant.reviewer.id if tenant.reviewer else None)
    print('Agencies:')
    for name, a in tenant.agencies.items():
        print('  {}: {}'.format(name, a.id))
    
    # Create tokens
    organizer_token = create_access_token(sub=tenant.organizer.id, tenant_id=tenant.tenant.id, role=UserRole.ORGANIZER.value)
    admin_token = create_access_token(sub=tenant.admin.id, tenant_id=tenant.tenant.id, role=UserRole.CITY_ADMIN.value)
    reviewer_token = create_access_token(sub=tenant.reviewer.id, tenant_id=tenant.tenant.id, role=UserRole.AGENCY_REVIEWER.value)
    
    client = TestClient(app)
    
    # Create agency as admin
    headers_admin = {'Authorization': 'Bearer ' + admin_token}
    create_agency = client.post('/admin/agencies', json={'name': 'Review Agency'}, headers=headers_admin)
    print('Create agency:', create_agency.status_code)
    if create_agency.status_code == 201:
        agency_id = create_agency.json()['id']
        print('Agency ID:', agency_id)
        
        # Add routing rule
        routing = client.post('/admin/routing', json={'event_type': 'Marathon', 'agency_id': agency_id}, headers=headers_admin)
        print('Routing:', routing.status_code)
        if routing.status_code == 201:
            print('Routing created')
            
            # Create application as organizer
            headers_org = {'Authorization': 'Bearer ' + organizer_token}
            START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
            END = START + timedelta(hours=6)
            draft = client.post('/applications', json={
                'event_name': 'Test Event',
                'event_type': EventType.MARATHON.value,
                'start_date': START.isoformat(),
                'end_date': END.isoformat(),
                'location': 'Test Location',
                'expected_attendance': 1000,
                'description': 'Test',
            }, headers=headers_org)
            print('Draft:', draft.status_code)
            if draft.status_code == 201:
                app_id = draft.json()['id']
                print('App ID:', app_id)
                
                # Submit
                submit = client.post('/applications/' + app_id + '/submit', headers=headers_org)
                print('Submit:', submit.status_code)
                if submit.status_code == 200:
                    print('Required agencies:', submit.json()['required_agencies'])
                    
                    # Check review tasks
                    reviewer_token2 = create_access_token(sub=tenant.reviewer.id, tenant_id=tenant.tenant.id, role=UserRole.AGENCY_REVIEWER.value)
                    headers_reviewer = {'Authorization': 'Bearer ' + reviewer_token2}
                    tasks = client.get('/review-tasks', headers=headers_reviewer)
                    print('Review tasks:', tasks.status_code)
                    if tasks.status_code == 200:
                        for t in tasks.json():
                            print('  Task agency_id: {} status: {}'.format(t['agency_id'], t['review_status']))
finally:
    db.close()