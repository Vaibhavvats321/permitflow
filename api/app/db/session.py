from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from contextlib import contextmanager
from sqlalchemy import text
from sqlalchemy.orm import Session

@contextmanager
def set_tenant_context(session: Session, tenant_id: str):
    """
    Sets the transaction-local PostgreSQL setting for RLS.
    Must be used within an active transaction context.
    """
    session.execute(text("SET LOCAL app.current_tenant_id = :tenant_id"), {"tenant_id": tenant_id})
    try:
        yield
    finally:
        # SET LOCAL is naturally scoped to the transaction, so it is automatically cleared on commit/rollback.
        pass
