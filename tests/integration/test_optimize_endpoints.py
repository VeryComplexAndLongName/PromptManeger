"""Tests for POST /optimize/greaterprompt and POST /optimize/llm endpoints.

The actual optimizer services are mocked so tests run without a GPU, a local
LLM, or any external API key.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from optimizer_service import set_runtime_optimizer_config


def login_as(client, username: str, password: str) -> str:  # type: ignore[no-untyped-def]
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PAYLOAD = {
    "task": "Generate a concise product description",
    "role": "You are a professional copywriter",
    "context": "E-commerce platform, consumer electronics",
    "constraints": "Max 50 words",
    "output_format": "Plain text",
    "examples": "Input: headphones → Output: Premium wireless headphones.",
}

MINIMAL_PAYLOAD = {"task": "Do something"}


def _make_result(engine: str = "greaterprompt-light") -> MagicMock:
    result = MagicMock()
    result.engine = engine
    result.optimized_fields = {
        "role": "Optimised role",
        "task": "Optimised task",
        "context": "Optimised context",
        "constraints": None,
        "output_format": None,
        "examples": None,
    }
    result.optimized_markdown = "## Optimised\n- Optimised task"
    result.notes = ["note-a", "note-b"]
    return result


# ---------------------------------------------------------------------------
# POST /optimize/greaterprompt
# ---------------------------------------------------------------------------


def test_greaterprompt_missing_task_returns_422(client):  # type: ignore[no-untyped-def]
    response = client.post("/optimize/greaterprompt", json={"role": "assistant"})
    assert response.status_code == 422


def test_greaterprompt_empty_body_returns_422(client):  # type: ignore[no-untyped-def]
    response = client.post("/optimize/greaterprompt", json={})
    assert response.status_code == 422


def test_greaterprompt_minimal_payload_returns_200(client):  # type: ignore[no-untyped-def]
    with patch("main.optimize_with_greaterprompt", return_value=_make_result()):
        response = client.post("/optimize/greaterprompt", json=MINIMAL_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "greaterprompt-light"
    assert "optimized" in body
    assert "optimized_markdown" in body
    assert "notes" in body


def test_greaterprompt_full_payload_returns_correct_shape(client):  # type: ignore[no-untyped-def]
    with patch("main.optimize_with_greaterprompt", return_value=_make_result()) as mock_svc:
        response = client.post("/optimize/greaterprompt", json=VALID_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "greaterprompt-light"
    assert body["optimized"]["task"] == "Optimised task"
    assert body["optimized_markdown"] != ""
    assert body["notes"] == ["note-a", "note-b"]
    mock_svc.assert_called_once()


def test_greaterprompt_service_receives_correct_fields(client):  # type: ignore[no-untyped-def]
    """Endpoint must forward all prompt fields to the service."""
    with patch("main.optimize_with_greaterprompt", return_value=_make_result()) as mock_svc:
        client.post("/optimize/greaterprompt", json=VALID_PAYLOAD)
    called_with = mock_svc.call_args[0][0]
    assert called_with["task"] == VALID_PAYLOAD["task"]
    assert called_with["role"] == VALID_PAYLOAD["role"]
    assert called_with["context"] == VALID_PAYLOAD["context"]


def test_greaterprompt_optimized_fields_none_falls_back_to_empty(client):  # type: ignore[no-untyped-def]
    """When optimized_fields is not a dict the endpoint should not crash."""
    result = _make_result()
    result.optimized_fields = None  # type: ignore[assignment]
    with patch("main.optimize_with_greaterprompt", return_value=result):
        response = client.post("/optimize/greaterprompt", json=VALID_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["optimized"]["task"] == ""


def test_greaterprompt_optimized_fields_empty_dict_falls_back(client):  # type: ignore[no-untyped-def]
    result = _make_result()
    result.optimized_fields = {}
    with patch("main.optimize_with_greaterprompt", return_value=result):
        response = client.post("/optimize/greaterprompt", json=VALID_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["optimized"]["task"] == ""


def test_greaterprompt_service_error_returns_500(client):  # type: ignore[no-untyped-def]
    """An unhandled exception in the service layer must surface as a 500."""
    with TestClient(app, raise_server_exceptions=False) as no_raise_client:
        login_response = no_raise_client.post("/auth/login", json={"username": "admin", "password": "admin"})
        no_raise_client.headers.update({"Authorization": f"Bearer {login_response.json()['access_token']}"})
        with patch("main.optimize_with_greaterprompt", side_effect=RuntimeError("Model crashed")):
            response = no_raise_client.post("/optimize/greaterprompt", json=VALID_PAYLOAD)
    assert response.status_code == 500


def test_greaterprompt_endpoint_uses_selected_runtime_model_for_gradient_path(client, monkeypatch):  # type: ignore[no-untyped-def]
    selected_model = "google/gemma-2-9b-it"
    tokenizer_instance = object()
    model_instance = object()
    tokenizer_loader = MagicMock(return_value=tokenizer_instance)
    model_loader = MagicMock(return_value=model_instance)

    fake_transformers = ModuleType("transformers")

    class FakeAutoTokenizer:  # type: ignore[too-few-public-methods]
        from_pretrained = tokenizer_loader

    class FakeAutoModelForCausalLM:  # type: ignore[too-few-public-methods]
        from_pretrained = model_loader

    fake_transformers.AutoTokenizer = FakeAutoTokenizer
    fake_transformers.AutoModelForCausalLM = FakeAutoModelForCausalLM

    fake_greaterprompt = ModuleType("greaterprompt")

    class FakeGreaterDataloader:  # type: ignore[too-few-public-methods]
        def __init__(self, custom_inputs):
            self.custom_inputs = custom_inputs

    class FakeGreaterOptimizer:  # type: ignore[too-few-public-methods]
        def __init__(self, model, tokenizer, optimize_config):
            self.model = model
            self.tokenizer = tokenizer
            self.optimize_config = optimize_config

        def optimize(self, inputs, p_extractor, rounds):
            assert self.model is model_instance
            assert self.tokenizer is tokenizer_instance
            assert rounds == 2
            return {VALID_PAYLOAD["task"]: [("Sharper optimized task", 0.91)]}

    fake_greaterprompt.GreaterDataloader = FakeGreaterDataloader
    fake_greaterprompt.GreaterOptimizer = FakeGreaterOptimizer

    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "greaterprompt", fake_greaterprompt)

    set_runtime_optimizer_config(model_id=selected_model, gp_profile="ultra", rounds=2)

    response = client.post("/optimize/greaterprompt", json=VALID_PAYLOAD)

    assert response.status_code == 200
    tokenizer_loader.assert_called_once_with(selected_model)
    model_loader.assert_called_once_with(selected_model)
    body = response.json()
    assert body["engine"] == "greaterprompt-gradient:ultra"
    assert body["notes"][0] == f"GreaterPrompt model: {selected_model}"
    assert body["optimized"]["task"] == "Sharper optimized task."


def test_greaterprompt_endpoint_uses_personal_config_per_user(client):  # type: ignore[no-untyped-def]
    create_user_response = client.post(
        "/users",
        json={
            "username": "gp-dev",
            "password": "dev-pass",
            "role": "developer",
            "projects": ["payments"],
            "is_active": True,
        },
    )
    assert create_user_response.status_code == 200

    admin_update = client.put(
        "/optimize/config",
        json={
            "gp_profile": "ultra",
            "llm_provider": "openai",
            "llm_model": "gpt-4o",
            "llm_base_url": "https://api.openai.com/v1",
        },
    )
    assert admin_update.status_code == 200

    developer_token = login_as(client, "gp-dev", "dev-pass")
    developer_client = TestClient(client.app)
    developer_client.headers.update({"Authorization": f"Bearer {developer_token}"})

    developer_update = developer_client.put(
        "/optimize/config",
        json={
            "gp_profile": "quality",
            "llm_provider": "anthropic",
            "llm_model": "claude-3-haiku",
            "llm_base_url": "https://api.anthropic.com",
        },
    )
    assert developer_update.status_code == 200

    with patch("main.optimize_with_greaterprompt", return_value=_make_result()) as mock_svc:
        response = developer_client.post("/optimize/greaterprompt", json=MINIMAL_PAYLOAD)

    assert response.status_code == 200
    config_override = mock_svc.call_args[0][1]
    assert config_override["effective_gp_profile"] == "quality"
    assert config_override["effective_llm_model"] == "claude-3-haiku"


def test_llm_provider_model_discovery_uses_personal_config_per_user(client):  # type: ignore[no-untyped-def]
    create_user_response = client.post(
        "/users",
        json={
            "username": "provider-dev",
            "password": "dev-pass",
            "role": "developer",
            "projects": ["payments"],
            "is_active": True,
        },
    )
    assert create_user_response.status_code == 200

    developer_token = login_as(client, "provider-dev", "dev-pass")
    developer_client = TestClient(client.app)
    developer_client.headers.update({"Authorization": f"Bearer {developer_token}"})

    developer_update = developer_client.put(
        "/optimize/config",
        json={
            "llm_provider": "openai",
            "llm_model": "gpt-4.1-mini",
            "llm_base_url": "https://api.openai.com/v1",
            "llm_timeout_seconds": 17,
        },
    )
    assert developer_update.status_code == 200

    with patch("main.list_available_llm_models", return_value=["gpt-4.1-mini"]) as mock_list:
        response = developer_client.get("/optimize/providers/openai/models")

    assert response.status_code == 200
    kwargs = mock_list.call_args.kwargs
    assert kwargs["config_override"]["effective_llm_model"] == "gpt-4.1-mini"
    assert kwargs["config_override"]["effective_llm_timeout_seconds"] == 17


# ---------------------------------------------------------------------------
# POST /optimize/llm
# ---------------------------------------------------------------------------


def test_llm_missing_task_returns_422(client):  # type: ignore[no-untyped-def]
    response = client.post("/optimize/llm", json={"role": "assistant"})
    assert response.status_code == 422


def test_llm_empty_body_returns_422(client):  # type: ignore[no-untyped-def]
    response = client.post("/optimize/llm", json={})
    assert response.status_code == 422


def test_llm_minimal_payload_returns_200(client):  # type: ignore[no-untyped-def]
    with patch("main.optimize_with_llm", return_value=_make_result("llm-ollama:qwen2.5:0.5b")):
        response = client.post("/optimize/llm", json=MINIMAL_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert "llm" in body["engine"]
    assert "optimized" in body


def test_llm_full_payload_returns_correct_shape(client):  # type: ignore[no-untyped-def]
    with patch("main.optimize_with_llm", return_value=_make_result("llm-ollama:qwen2.5:0.5b")) as mock_svc:
        response = client.post("/optimize/llm", json=VALID_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["optimized"]["task"] == "Optimised task"
    assert body["notes"] == ["note-a", "note-b"]
    mock_svc.assert_called_once()


def test_llm_service_receives_correct_fields(client):  # type: ignore[no-untyped-def]
    with patch("main.optimize_with_llm", return_value=_make_result()) as mock_svc:
        client.post("/optimize/llm", json=VALID_PAYLOAD)
    called_with = mock_svc.call_args[0][0]
    assert called_with["task"] == VALID_PAYLOAD["task"]
    assert called_with["constraints"] == VALID_PAYLOAD["constraints"]


def test_llm_optimized_fields_none_falls_back_to_empty(client):  # type: ignore[no-untyped-def]
    result = _make_result("llm-fallback")
    result.optimized_fields = None  # type: ignore[assignment]
    with patch("main.optimize_with_llm", return_value=result):
        response = client.post("/optimize/llm", json=VALID_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["optimized"]["task"] == ""


def test_llm_optimized_fields_empty_dict_falls_back(client):  # type: ignore[no-untyped-def]
    result = _make_result("llm-fallback")
    result.optimized_fields = {}
    with patch("main.optimize_with_llm", return_value=result):
        response = client.post("/optimize/llm", json=VALID_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["optimized"]["task"] == ""


def test_llm_service_error_returns_500(client):  # type: ignore[no-untyped-def]
    with TestClient(app, raise_server_exceptions=False) as no_raise_client:
        login_response = no_raise_client.post("/auth/login", json={"username": "admin", "password": "admin"})
        no_raise_client.headers.update({"Authorization": f"Bearer {login_response.json()['access_token']}"})
        with patch("main.optimize_with_llm", side_effect=RuntimeError("LLM timeout")):
            response = no_raise_client.post("/optimize/llm", json=VALID_PAYLOAD)
    assert response.status_code == 500


def test_llm_fallback_engine_is_accepted(client):  # type: ignore[no-untyped-def]
    """When the real LLM is unavailable the service may return engine='llm-fallback'."""
    with patch("main.optimize_with_llm", return_value=_make_result("llm-fallback")):
        response = client.post("/optimize/llm", json=VALID_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["engine"] == "llm-fallback"
