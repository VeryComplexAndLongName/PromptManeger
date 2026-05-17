"""Tests for POST /optimize endpoint.

The optimizer service is mocked so tests run without external provider keys.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from main import app


def login_as(client, username: str, password: str) -> str:  # type: ignore[no-untyped-def]
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


VALID_PAYLOAD = {
    "task": "Generate a concise product description",
    "role": "You are a professional copywriter",
    "context": "E-commerce platform, consumer electronics",
    "constraints": "Max 50 words",
    "output_format": "Plain text",
    "examples": "Input: headphones -> Output: Premium wireless headphones.",
}

MINIMAL_PAYLOAD = {"task": "Do something"}


def _make_result(engine: str = "leo-openai:gpt-4o-mini") -> MagicMock:
    result = MagicMock()
    result.engine = engine
    result.optimized_fields = {
        "role": "Optimized role",
        "task": "Optimized task",
        "context": "Optimized context",
        "constraints": None,
        "output_format": None,
        "examples": None,
    }
    result.optimized_markdown = "## Optimized\n- Optimized task"
    result.notes = ["note-a", "note-b"]
    return result


def test_leo_missing_task_returns_422(client):  # type: ignore[no-untyped-def]
    response = client.post("/optimize", json={"role": "assistant"})
    assert response.status_code == 422


def test_leo_empty_body_returns_422(client):  # type: ignore[no-untyped-def]
    response = client.post("/optimize", json={})
    assert response.status_code == 422


def test_leo_minimal_payload_returns_200(client):  # type: ignore[no-untyped-def]
    with patch("main.optimize_prompt_with_active_backend", return_value=_make_result()):
        response = client.post("/optimize", json=MINIMAL_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["engine"].startswith("leo-")
    assert "optimized" in body
    assert "optimized_markdown" in body
    assert "notes" in body


def test_leo_full_payload_returns_correct_shape(client):  # type: ignore[no-untyped-def]
    with patch("main.optimize_prompt_with_active_backend", return_value=_make_result()) as mock_svc:
        response = client.post("/optimize", json=VALID_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["optimized"]["task"] == "Optimized task"
    assert body["optimized_markdown"] != ""
    assert body["notes"] == ["note-a", "note-b"]
    mock_svc.assert_called_once()


def test_leo_service_receives_correct_fields(client):  # type: ignore[no-untyped-def]
    with patch("main.optimize_prompt_with_active_backend", return_value=_make_result()) as mock_svc:
        client.post("/optimize", json=VALID_PAYLOAD)
    called_with = mock_svc.call_args[0][0]
    assert called_with["task"] == VALID_PAYLOAD["task"]
    assert called_with["role"] == VALID_PAYLOAD["role"]
    assert called_with["context"] == VALID_PAYLOAD["context"]


def test_leo_optimized_fields_none_falls_back_to_empty(client):  # type: ignore[no-untyped-def]
    result = _make_result()
    result.optimized_fields = None  # type: ignore[assignment]
    with patch("main.optimize_prompt_with_active_backend", return_value=result):
        response = client.post("/optimize", json=VALID_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["optimized"]["task"] == ""


def test_leo_service_error_returns_500(client):  # type: ignore[no-untyped-def]
    with TestClient(app, raise_server_exceptions=False) as no_raise_client:
        login_response = no_raise_client.post("/auth/login", json={"username": "admin", "password": "admin"})
        no_raise_client.headers.update({"Authorization": f"Bearer {login_response.json()['access_token']}"})
        with patch("main.optimize_prompt_with_active_backend", side_effect=RuntimeError("Provider failed")):
            response = no_raise_client.post("/optimize", json=VALID_PAYLOAD)
    assert response.status_code == 500


def test_leo_endpoint_uses_personal_config_per_user(client):  # type: ignore[no-untyped-def]
    create_user_response = client.post(
        "/users",
        json={
            "username": "leo-dev",
            "password": "dev-pass",
            "role": "developer",
            "projects": ["payments"],
            "is_active": True,
        },
    )
    assert create_user_response.status_code == 200

    developer_token = login_as(client, "leo-dev", "dev-pass")
    developer_client = TestClient(client.app)
    developer_client.headers.update({"Authorization": f"Bearer {developer_token}"})

    developer_update = developer_client.put(
        "/optimize/config",
        json={
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
            "llm_base_url": "https://api.openai.com/v1",
        },
    )
    assert developer_update.status_code == 200

    with patch("main.optimize_prompt_with_active_backend", return_value=_make_result()) as mock_svc:
        response = developer_client.post("/optimize", json=MINIMAL_PAYLOAD)

    assert response.status_code == 200
    config_override = mock_svc.call_args[0][1]
    assert config_override["effective_llm_provider"] == "openai"
    assert config_override["effective_llm_model"] == "gpt-4o-mini"
