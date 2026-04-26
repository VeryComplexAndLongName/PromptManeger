import os
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./prompts.db")

is_sqlite = SQLALCHEMY_DATABASE_URL.startswith("sqlite")

engine_kwargs: dict[str, Any] = {
    "pool_pre_ping": True,
}

if is_sqlite:
    engine_kwargs.update(
        {
            "connect_args": {
                "check_same_thread": False,
                "timeout": 30,
            },
        }
    )
else:
    engine_kwargs.update(
        {
            "pool_size": 20,
            "max_overflow": 40,
            "pool_timeout": 30,
            "pool_recycle": 1800,
        }
    )

engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_kwargs)


if is_sqlite:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
