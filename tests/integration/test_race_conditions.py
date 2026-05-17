from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import auth_service
import main
from database import Base
from main import app, get_db
from models import Prompt, Tag


def test_http_concurrent_create_prompt_with_shared_new_tag_is_race_safe(tmp_path: Path):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "race_http.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Iterator[Session]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    original_session_local = main.SessionLocal
    original_init_database = main.init_database

    try:
        main.SessionLocal = testing_session_local
        main.init_database = lambda bind=None: Base.metadata.create_all(bind=engine)
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[auth_service.get_db_session] = override_get_db

        with TestClient(app) as admin_client:
            login_response = admin_client.post(
                "/auth/login",
                json={"username": "admin", "password": "admin"},
            )
            assert login_response.status_code == 200
            token = login_response.json()["access_token"]

            run_id = "race-http"
            create_project_response = admin_client.post(
                "/projects",
                headers={"Authorization": f"Bearer {token}"},
                json={"name": f"project-{run_id}"},
            )
            assert create_project_response.status_code == 200

            def _worker(index: int) -> tuple[int, int]:
                with TestClient(app) as worker_client:
                    worker_client.headers.update({"Authorization": f"Bearer {token}"})
                    payload = {
                        "name": f"prompt-{run_id}-{index}",
                        "project": f"project-{run_id}",
                        "tags": [f"shared-tag-{run_id}"],
                        "role": "assistant",
                        "task": f"task-{run_id}-{index}",
                        "context": f"context-{run_id}-{index}",
                        "constraints": "none",
                        "output_format": "text",
                        "examples": f"example-{run_id}-{index}",
                    }
                    create_response = worker_client.post("/prompts", json=payload)
                    list_response = worker_client.get("/prompts", params={"project": f"project-{run_id}"})
                    return create_response.status_code, list_response.status_code

            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(_worker, range(12)))

            assert all(create_status == 200 for create_status, _ in results), results
            assert all(list_status == 200 for _, list_status in results), results

        verify_session = testing_session_local()
        try:
            prompts_count = verify_session.query(Prompt).filter(Prompt.name.like("prompt-race-http-%")).count()
            tags_count = verify_session.query(Tag).filter(Tag.name == "shared-tag-race-http").count()
            assert prompts_count == 12
            assert tags_count == 1
        finally:
            verify_session.close()
    finally:
        main.SessionLocal = original_session_local
        main.init_database = original_init_database
        app.dependency_overrides.clear()
        engine.dispose()
