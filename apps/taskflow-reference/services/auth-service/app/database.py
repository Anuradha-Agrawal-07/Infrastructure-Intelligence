import os
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://appuser:apppassword@postgres:5432/appdb",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def wait_for_db(max_retries: int = 30, delay_seconds: float = 1.0) -> None:
    """Block until PostgreSQL accepts connections. Used at service startup
    so the auth-service comes up cleanly even if Postgres is still
    initializing inside its own container."""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(delay_seconds)
    raise RuntimeError(
        f"auth-service could not reach PostgreSQL after {max_retries} attempts"
    ) from last_error


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
