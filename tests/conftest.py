import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import auth_service
import main

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import Base
from main import app, get_db
from optimizer_service import clear_runtime_model_id, set_runtime_optimizer_config


@pytest.fixture(scope="session")
def engine():  # type: ignore[no-untyped-def]
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    return test_engine


@pytest.fixture(scope="function")
def db_session(engine) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(scope="function")
def client(db_session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield db_session

    startup_session_factory = sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind())
    original_session_local = main.SessionLocal
    original_init_database = main.init_database

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[auth_service.get_db_session] = override_get_db
    main.SessionLocal = startup_session_factory
    main.init_database = lambda bind=None: Base.metadata.create_all(bind=db_session.get_bind())
    with TestClient(app) as test_client:
        login_response = test_client.post(
            "/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        if login_response.status_code != 200:
            raise AssertionError(f"Login failed: {login_response.status_code} {login_response.text}")

        token = login_response.json()["access_token"]
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client
    main.SessionLocal = original_session_local
    main.init_database = original_init_database
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_runtime_optimizer_config() -> Iterator[None]:
    clear_runtime_model_id()
    set_runtime_optimizer_config(
        rounds=2,
        gp_profile="fast",
        llm_provider="ollama",
        llm_model="qwen2.5:0.5b",
        llm_base_url="http://127.0.0.1:11434",
        llm_timeout_seconds=300,
    )
    yield


@pytest.fixture
def sample_prompt_payload() -> dict[str, object]:
    return {
        "name": "checkout-system",
        "project": "payments",
        "tags": ["system", "production"],
        "role": "You are a payments assistant",
        "task": "Generate checkout validation rules",
        "context": "Target country: US",
        "constraints": "No PII in output",
        "output_format": "Markdown bullet list",
        "examples": "Input: card=visa, amount=10",
    }
