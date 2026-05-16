"""Tests for POST /optimize/greaterprompt and POST /optimize/llm endpoints.

The actual optimizer services are mocked so tests run without a GPU, a local
LLM, or any external API key.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app

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
        with patch("main.optimize_with_greaterprompt", side_effect=RuntimeError("Model crashed")):
            response = no_raise_client.post("/optimize/greaterprompt", json=VALID_PAYLOAD)
    assert response.status_code == 500


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
        with patch("main.optimize_with_llm", side_effect=RuntimeError("LLM timeout")):
            response = no_raise_client.post("/optimize/llm", json=VALID_PAYLOAD)
    assert response.status_code == 500


def test_llm_fallback_engine_is_accepted(client):  # type: ignore[no-untyped-def]
    """When the real LLM is unavailable the service may return engine='llm-fallback'."""
    with patch("main.optimize_with_llm", return_value=_make_result("llm-fallback")):
        response = client.post("/optimize/llm", json=VALID_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["engine"] == "llm-fallback"
