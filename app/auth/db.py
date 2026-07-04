import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.auth.models import Base, User

# Default host port is 5433, not Postgres's usual 5432 — many dev machines already
# run a native Postgres service on 5432 (this one included), so this app's own
# container avoids that port entirely rather than fighting over it.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/askmydocs")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Seeded, pre-verified demo account for the frontend's "Log in as Guest / Demo"
# button (Frontend/src/components/Auth.jsx) — kept in sync with that file manually,
# since frontend/backend are separate processes with no shared config source.
DEMO_EMAIL = "demo@askmydocs.app"
DEMO_PASSWORD = "DemoPass123!"


def _migrate_users_table():
    """Idempotent column additions for schema changes made after the initial
    create_all — safe to run on every startup, including brand-new databases."""
    with engine.connect() as conn:
        for ddl in (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expiry TIMESTAMP",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP",
        ):
            conn.execute(text(ddl))
        conn.commit()


def _seed_demo_user():
    """Idempotent: create the demo account once, on the first startup that
    doesn't already have it. Pre-verified/active since SMTP is off — the demo
    account can't go through the normal email-verification flow."""
    from app.auth.utils import hash_password

    with SessionLocal() as db:
        if db.query(User).filter(User.email == DEMO_EMAIL).first():
            return
        db.add(User(
            email=DEMO_EMAIL,
            hashed_password=hash_password(DEMO_PASSWORD),
            role="user",
            is_active=True,
            is_verified=True,
        ))
        db.commit()


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_users_table()
    _seed_demo_user()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
