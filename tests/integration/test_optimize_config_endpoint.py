def test_get_and_update_optimize_config(client):  # type: ignore[no-untyped-def]
    get_response = client.get("/optimize/config")
    assert get_response.status_code == 200
    cfg = get_response.json()
    assert cfg["effective_llm_provider"] == "ollama"

    put_response = client.put(
        "/optimize/config",
        json={
            "llm_provider": "ollama",
            "llm_model": "qwen2.5:0.5b",
            "llm_base_url": "http://127.0.0.1:11434",
            "llm_timeout_seconds": 450,
        },
    )
    assert put_response.status_code == 200
    updated = put_response.json()
    assert updated["effective_llm_timeout_seconds"] == 450


# ---------------------------------------------------------------------------
# PUT /optimize/config — token and partial-update edge cases
# ---------------------------------------------------------------------------


def test_update_config_with_api_token_sets_has_token_flag(client):  # type: ignore[no-untyped-def]
    response = client.put("/optimize/config", json={"llm_api_token": "my-secret-token"})
    assert response.status_code == 200
    cfg = response.json()
    assert cfg["runtime_has_llm_api_token"] is True
    assert cfg["effective_has_llm_api_token"] is True


def test_update_config_api_token_never_returned_in_response(client):  # type: ignore[no-untyped-def]
    """The actual token value must never appear in any response field."""
    client.put("/optimize/config", json={"llm_api_token": "supersecret"})
    response = client.get("/optimize/config")
    assert response.status_code == 200
    assert "supersecret" not in response.text


def test_update_config_only_llm_model_preserves_other_fields(client):  # type: ignore[no-untyped-def]
    client.put("/optimize/config", json={"llm_model": "custom-model", "llm_provider": "ollama"})
    response = client.put("/optimize/config", json={"llm_timeout_seconds": 120})
    assert response.status_code == 200
    cfg = response.json()
    assert cfg["effective_llm_timeout_seconds"] == 120
    assert cfg["runtime_llm_model"] == "custom-model"


def test_update_config_llm_base_url(client):  # type: ignore[no-untyped-def]
    response = client.put(
        "/optimize/config",
        json={"llm_base_url": "http://my-ollama:11434"},
    )
    assert response.status_code == 200
    cfg = response.json()
    assert cfg["runtime_llm_base_url"] == "http://my-ollama:11434"
    assert cfg["effective_llm_base_url"] == "http://my-ollama:11434"


def test_update_config_accepts_known_providers(client):  # type: ignore[no-untyped-def]
    for provider in ("ollama", "openai", "anthropic"):
        response = client.put("/optimize/config", json={"llm_provider": provider})
        assert response.status_code == 200
        cfg = response.json()
        assert cfg["runtime_llm_provider"] == provider


def test_update_config_unknown_provider_is_accepted(client):  # type: ignore[no-untyped-def]
    """Unknown provider names are stored as-is; validation is not enforced at this layer."""
    response = client.put("/optimize/config", json={"llm_provider": "turbo"})
    assert response.status_code == 200


def test_update_config_llm_timeout_minimum_is_five(client):  # type: ignore[no-untyped-def]
    """Values below 5 are clamped to 5 by the service layer."""
    response = client.put("/optimize/config", json={"llm_timeout_seconds": 1})
    assert response.status_code == 200
    assert response.json()["effective_llm_timeout_seconds"] >= 5


def test_get_config_returns_all_required_fields(client):  # type: ignore[no-untyped-def]
    response = client.get("/optimize/config")
    assert response.status_code == 200
    body = response.json()
    required_keys = {
        "effective_llm_provider",
        "effective_llm_model",
        "effective_llm_base_url",
        "effective_llm_timeout_seconds",
        "effective_has_llm_api_token",
        "runtime_has_llm_api_token",
        "env_has_llm_api_token",
    }
    for key in required_keys:
        assert key in body, f"Missing field: {key}"


# ---------------------------------------------------------------------------
# GET /optimize/providers/{provider}/models — discovery edge cases
# ---------------------------------------------------------------------------


def test_get_provider_models_anthropic_returns_fixed_list(client):  # type: ignore[no-untyped-def]
    response = client.get("/optimize/providers/anthropic/models")
    assert response.status_code == 200
    models = response.json()
    assert isinstance(models, list)
    assert len(models) > 0
    assert all(isinstance(m, str) for m in models)
    assert any("claude" in m for m in models)


def test_get_provider_models_unknown_provider_returns_empty_list(client):  # type: ignore[no-untyped-def]
    response = client.get("/optimize/providers/doesnotexist/models")
    assert response.status_code == 200
    assert response.json() == []


def test_get_provider_models_ollama_unreachable_returns_empty_list(client):  # type: ignore[no-untyped-def]
    """Connecting to a port nothing listens on must not raise — returns []."""
    response = client.get(
        "/optimize/providers/ollama/models",
        params={"base_url": "http://127.0.0.1:19998", "timeout_seconds": 1},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_get_provider_models_timeout_too_small_returns_422(client):  # type: ignore[no-untyped-def]
    response = client.get("/optimize/providers/ollama/models", params={"timeout_seconds": 0})
    assert response.status_code == 422


def test_get_provider_models_timeout_too_large_returns_422(client):  # type: ignore[no-untyped-def]
    response = client.get("/optimize/providers/ollama/models", params={"timeout_seconds": 99})
    assert response.status_code == 422


def test_get_provider_models_openai_without_token_returns_empty_list(client):  # type: ignore[no-untyped-def]
    """OpenAI discovery requires a token; without one the service returns []."""
    response = client.get("/optimize/providers/openai/models", params={"timeout_seconds": 2})
    assert response.status_code == 200
    assert response.json() == []


def test_get_provider_models_openai_mocked_with_token(client):  # type: ignore[no-untyped-def]
    from unittest.mock import patch

    with patch(
        "main.list_available_models",
        return_value=["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
    ) as mock_list:
        response = client.get(
            "/optimize/providers/openai/models",
            params={"api_token": "test-token", "timeout_seconds": 5},
        )
    assert response.status_code == 200
    models = response.json()
    assert "gpt-4o" in models
    called_args, called_kwargs = mock_list.call_args
    assert called_args == ("openai",)
    assert called_kwargs["base_url"] is None
    assert called_kwargs["timeout_seconds"] == 5
    assert called_kwargs["api_token"] == "test-token"
    assert "config_override" in called_kwargs


def test_get_provider_models_case_insensitive_provider(client):  # type: ignore[no-untyped-def]
    """Provider name normalisation — 'ANTHROPIC' should work the same as 'anthropic'."""
    upper = client.get("/optimize/providers/ANTHROPIC/models")
    lower = client.get("/optimize/providers/anthropic/models")
    assert upper.status_code == 200
    assert lower.status_code == 200
    assert upper.json() == lower.json()
