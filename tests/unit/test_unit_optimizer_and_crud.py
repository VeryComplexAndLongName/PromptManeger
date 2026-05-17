import sys
from concurrent.futures import ThreadPoolExecutor
from types import ModuleType

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
    _normalize_text,
    _parse_ollama_json_response,
    optimize_with_greaterprompt,
    _to_prompt_fields,
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


def test_to_prompt_fields_falls_back_when_values_missing():  # type: ignore[no-untyped-def]
    raw = {"role": {"nested": "assistant"}, "task": None, "context": ["x", "y"]}
    fallback: dict[str, str | None] = {
        "role": "fallback-role",
        "task": "fallback-task",
        "context": "fallback-context",
        "constraints": "fallback-constraints",
        "output_format": "fallback-output",
        "examples": "fallback-examples",
    }

    result = _to_prompt_fields(raw, fallback)

    assert result["role"] == '{"nested": "assistant"}'
    assert result["task"] == "fallback-task"
    assert result["context"] == '["x", "y"]'
    assert result["constraints"] == "fallback-constraints"


def test_parse_ollama_json_response_recovers_unescaped_newlines():  # type: ignore[no-untyped-def]
    raw_response = '{\n  "role": "assistant",\n  "task": "Line one\nLine two",\n  "context": "extra"\n}'

    parsed = _parse_ollama_json_response(raw_response)

    assert parsed["role"] == "assistant"
    assert parsed["task"] == "Line one\nLine two"
    assert parsed["context"] == "extra"


def test_parse_ollama_json_response_recovers_truncated_payload():  # type: ignore[no-untyped-def]
    raw_response = '{"role":"assistant","task":"Short task","context":"Trimmed but usable'

    parsed = _parse_ollama_json_response(raw_response)

    assert parsed["role"] == "assistant"
    assert parsed["task"] == "Short task"
    assert parsed["context"] == "Trimmed but usable"


def test_runtime_config_applies_quality_profile():  # type: ignore[no-untyped-def]
    set_runtime_optimizer_config(gp_profile="quality", rounds=3)

    cfg = get_runtime_optimizer_config()

    assert cfg["effective_gp_profile"] == "quality"
    assert cfg["effective_rounds"] == 3
    assert cfg["effective_gp_optimize_config"]["candidates_topk"] == 8
    assert cfg["effective_gp_optimize_config"]["filter"] is True


def test_greaterprompt_lightweight_notes_report_active_runtime(monkeypatch):  # type: ignore[no-untyped-def]
    fake_greaterprompt = ModuleType("greaterprompt")

    class FakeGreaterDataloader:  # type: ignore[too-few-public-methods]
        def __init__(self, custom_inputs):
            self.custom_inputs = custom_inputs

    fake_greaterprompt.GreaterDataloader = FakeGreaterDataloader

    fake_utils = ModuleType("greaterprompt.utils")

    def fake_clean_string(items):
        return items

    fake_utils.clean_string = fake_clean_string

    monkeypatch.setitem(sys.modules, "greaterprompt", fake_greaterprompt)
    monkeypatch.setitem(sys.modules, "greaterprompt.utils", fake_utils)

    set_runtime_optimizer_config(model_id=None, gp_profile="ultra", rounds=2)

    result = optimize_with_greaterprompt({"task": "Refine this prompt"})

    assert result.engine == "greaterprompt-light"
    assert result.notes[0] == "GreaterPrompt model: none (lightweight mode)"
    assert result.notes[1] == "GreaterPrompt profile: ultra | Rounds: 2"


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

    assert [role.name for role in roles] == ["admin", "developer"]


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
