import uuid
from datetime import UTC, datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.models import EventType
import sqlalchemy as sa
from app.core.config import settings
from app.db.session import engine
from sqlalchemy.orm import Session
from app.core.security import create_access_token, hash_password
from app.models import User, UserRole, Agency, Application, ApplicationStatus, ReviewTask, ReviewStatus

admin_engine = sa.create_engine(settings.DATABASE_URL_ADMIN, future=True)
factory = sa.orm.sessionmaker(bind=admin_engine, autoflush=False)
db = factory()

try:
    from tests.conftest import TenantFixture, TEST_PASSWORD
    tenant = TenantFixture(db, 'DebugAvg3', with_reviewer=True)
    db.commit()
    
    print('Tenant:', tenant.tenant.id)
    print('Organizer:', tenant.organizer.id)
    print('Reviewer:', tenant.reviewer.id)
    print('Agencies:')
    for name, a in tenant.agencies.items():
        print('  {}: {}'.format(name, a.id))
    
    # Remove Health from Marathon routing
    admin_token = create_access_token(sub=tenant.admin.id, tenant_id=tenant.tenant.id, role='City Admin')
    headers_admin = {'Authorization': 'Bearer ' + admin_token}
    health_id = str(tenant.agencies['Health'].id)
    client = TestClient(app)
    delete_resp = client.delete('/admin/routing/Marathon/' + health_id, headers={'Authorization': 'Bearer ' + admin_token})
    print('Delete Health routing:', delete_resp.status_code)
    
    # Create application as organizer
    organizer_token = create_access_token(sub=tenant.organizer.id, tenant_id=tenant.tenant.id, role='Organizer')
    headers_org = {'Authorization': 'Bearer ' + organizer_token}
    START = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
    END = START + timedelta(hours=6)
    draft = client.post('/applications', json={
        'event_name': 'Debug Avg',
        'event_type': EventType.MARATHON.value,
        'start_date': START.isoformat(),
        'end_date': END.isoformat(),
        'location': 'Test',
        'expected_attendance': 1000,
        'description': 'Test',
    }, headers=headers_org)
    print('Draft:', draft.status_code)
    if draft.status_code == 201:
        app_id = draft.json()['id']
        
        # Submit
        submit = client.post('/applications/' + app_id + '/submit', headers={'Authorization': 'Bearer ' + organizer_token})
        print('Submit:', submit.status_code)
        if submit.status_code == 200:
            print('Required agencies:', submit.json()['required_agencies'])
            app_id = submit.json()['application']['id']
            
            # Check review tasks
            reviewer_token2 = create_access_token(sub=tenant.reviewer.id, tenant_id=tenant.tenant.id, role='Agency Reviewer')
            headers_reviewer = {'Authorization': 'Bearer ' + reviewer_token2}
            tasks = client.get('/review-tasks', headers=headers_reviewer)
            print('Review tasks:', tasks.status_code)
            if tasks.status_code == 200:
                for t in tasks.json():
                    print('  Task agency_id: {} status: {}'.format(t['agency_id'], t['review_status']))
                
                # Approve
                for t in tasks.json():
                    approve = client.post('/review-tasks/' + t['id'] + '/decision', json={'action': 'approve', 'comment': 'OK'}, headers={'Authorization': 'Bearer ' + reviewer_token2})
                    print('  Approve:', approve.status_code, 'app_status:', approve.json().get('application_status', 'N/A'))
                
                # Check dashboard
                admin_token2 = create_access_token(sub=tenant.admin.id, tenant_id=tenant.tenant.id, role='City Admin')
                dash = client.get('/admin/dashboard', headers={'Authorization': 'Bearer ' + admin_token2})
                print('Dashboard:', dash.status_code, dash.json())
finally:
    db.close()