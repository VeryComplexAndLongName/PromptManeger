from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import insert
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import crud
import auth_service
from database import Base, init_database
from models import Project, Prompt, Role, Tag
from optimizer_service import (
    LeoPromptOptimizerBackend,
    _normalize_text,
    _parse_structured_response,
    optimize_prompt_with_active_backend,
    get_runtime_optimizer_config,
    set_runtime_optimizer_config,
)


def test_normalize_tags_deduplicates_and_sorts():  # type: ignore[no-untyped-def]
    tags = [" Prod ", "alpha", "prod", "", "Beta"]

    normalized = crud.normalize_tags(tags)

    assert normalized == ["alpha", "beta", "prod"]


def test_normalize_text_handles_non_string_types():  # type: ignore[no-untyped-def]
    assert _normalize_text({"a": 1}) == '{"a": 1}'
    assert _normalize_text(["x", 2]) == '["x", 2]'
    assert _normalize_text(42) == "42"


def test_parse_structured_response_uses_fallbacks():  # type: ignore[no-untyped-def]
    raw_response = "Task: Improved task\nConstraints: Keep short"
    fallback: dict[str, str | None] = {
        "role": "assistant",
        "task": "fallback task",
        "context": "fallback context",
        "constraints": "fallback constraints",
        "output_format": "fallback output",
        "examples": "fallback examples",
    }

    parsed = _parse_structured_response(raw_response, fallback)

    assert parsed["role"] == "assistant"
    assert parsed["task"] == "Improved task."
    assert parsed["constraints"] == "Keep short"
    assert parsed["context"] == "fallback context"


def test_runtime_config_applies_llm_model():  # type: ignore[no-untyped-def]
    set_runtime_optimizer_config(llm_model="llama3:8b", llm_provider="ollama")

    cfg = get_runtime_optimizer_config()

    assert cfg["effective_llm_model"] == "llama3:8b"
    assert cfg["effective_llm_provider"] == "ollama"


def test_optimize_backend_fallback_when_provider_missing_token():  # type: ignore[no-untyped-def]
    set_runtime_optimizer_config(llm_provider="anthropic", llm_model="claude-3-haiku", llm_api_token="")

    result = optimize_prompt_with_active_backend({"task": "Refine this prompt"})

    assert "fallback" in result.engine
    assert result.optimized_fields["task"]


def test_openai_provider_with_ollama_base_url_is_treated_as_compat_mode():  # type: ignore[no-untyped-def]
    backend = LeoPromptOptimizerBackend()

    assert backend._looks_like_ollama_base_url("http://127.0.0.1:11434") is True
    assert backend._looks_like_ollama_base_url("http://localhost:11434") is True
    assert backend._looks_like_ollama_base_url("https://api.openai.com/v1") is False


def test_openai_provider_with_ollama_base_url_returns_ollama_models(client):  # type: ignore[no-untyped-def]
    response = client.get(
        "/optimize/providers/openai/models",
        params={"base_url": "http://127.0.0.1:19998", "timeout_seconds": 1},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_pick_low_memory_ollama_model_prefers_smallest_available():  # type: ignore[no-untyped-def]
    backend = LeoPromptOptimizerBackend()
    models = ["deepseek-r1:latest", "qwen2.5:0.5b", "qwen2.5:1.5b"]

    selected = backend._pick_low_memory_ollama_model(models, "deepseek-r1:latest")

    assert selected == "qwen2.5:0.5b"


@pytest.mark.parametrize(
    ("name",),
    [(None,), ("",)],
)
def test_prompt_requires_non_empty_name_in_db(engine, name):  # type: ignore[no-untyped-def]
    connection = engine.connect()
    transaction = connection.begin()
    project_insert = insert(Project).values(name="payments")
    project_id = connection.execute(project_insert).inserted_primary_key[0]
    with pytest.raises(IntegrityError):
        connection.execute(insert(Prompt).values(name=name, project_id=project_id))

    transaction.rollback()
    connection.close()


@pytest.mark.parametrize(("project_name",), [(None,), ("",), ("   ",)])
def test_project_requires_non_empty_name_in_db(engine, project_name):  # type: ignore[no-untyped-def]
    connection = engine.connect()
    transaction = connection.begin()
    with pytest.raises(IntegrityError):
        connection.execute(insert(Project).values(name=project_name))

    transaction.rollback()
    connection.close()


def test_init_database_creates_auth_tables(engine):  # type: ignore[no-untyped-def]
    Base.metadata.drop_all(bind=engine)

    init_database(bind=engine)

    tables = set(Base.metadata.tables)
    inspector = engine.dialect.get_table_names(engine.connect())

    assert "users" in tables
    assert "configs" in tables
    assert "project_access" in tables
    assert "users" in inspector
    assert "configs" in inspector
    assert "project_access" in inspector


def test_maybe_bootstrap_admin_creates_default_admin(db_session):  # type: ignore[no-untyped-def]
    auth_service.maybe_bootstrap_admin(db_session)

    admin_user = crud.get_user_by_username(db_session, "admin")

    assert admin_user is not None
    assert admin_user.role == "admin"
    assert auth_service.authenticate_user(db_session, "admin", "admin") is not None


def test_init_database_and_bootstrap_seed_default_roles(db_session):  # type: ignore[no-untyped-def]
    auth_service.maybe_bootstrap_admin(db_session)

    roles = db_session.query(Role).order_by(Role.name.asc()).all()

    assert [role.name for role in roles] == ["admin", "developer", "viewer"]


def test_concurrent_create_prompt_with_shared_new_tag_is_race_safe(tmp_path):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "race_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    try:
        bootstrap_session = SessionLocal()
        try:
            crud.get_or_create_project(bootstrap_session, "race-project")
            bootstrap_session.commit()
        finally:
            bootstrap_session.close()

        def _worker(index: int) -> tuple[bool, str | None]:
            session = SessionLocal()
            try:
                crud.create_prompt(
                    session,
                    name=f"race-prompt-{index}",
                    project="race-project",
                    task=f"task-{index}",
                    role="assistant",
                    context=f"context-{index}",
                    constraints="none",
                    output_format="text",
                    examples=f"example-{index}",
                    tags=["race-shared-tag"],
                )
                return True, None
            except Exception as exc:  # pragma: no cover - captures unexpected race failures
                return False, str(exc)
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(_worker, range(12)))

        failures = [error for ok, error in results if not ok]
        assert failures == []

        verify_session = SessionLocal()
        try:
            prompts_count = verify_session.query(Prompt).filter(Prompt.name.like("race-prompt-%")).count()
            tags_count = verify_session.query(Tag).filter(Tag.name == "race-shared-tag").count()
            assert prompts_count == 12
            assert tags_count == 1
        finally:
            verify_session.close()
    finally:
        engine.dispose()
