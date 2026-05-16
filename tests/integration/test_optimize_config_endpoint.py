def test_get_and_update_optimize_config(client):  # type: ignore[no-untyped-def]
    get_response = client.get("/optimize/config")
    assert get_response.status_code == 200
    cfg = get_response.json()
    assert cfg["effective_gp_profile"] in {"fast", "quality"}
    assert cfg["effective_llm_provider"] == "ollama"

    put_response = client.put(
        "/optimize/config",
        json={
            "model_id": "meta-llama/Llama-3.2-1B-Instruct",
            "rounds": 4,
            "gp_profile": "quality",
            "llm_provider": "ollama",
            "llm_model": "qwen2.5:0.5b",
            "llm_base_url": "http://127.0.0.1:11434",
            "llm_timeout_seconds": 450,
        },
    )
    assert put_response.status_code == 200
    updated = put_response.json()
    assert updated["runtime_model_id"] == "meta-llama/Llama-3.2-1B-Instruct"
    assert updated["runtime_rounds"] == 4
    assert updated["runtime_gp_profile"] == "quality"
    assert updated["effective_llm_timeout_seconds"] == 450

    clear_response = client.put(
        "/optimize/config",
        json={
            "clear_model_id": True,
            "gp_profile": "fast",
            "rounds": 2,
        },
    )
    assert clear_response.status_code == 200
    cleared = clear_response.json()
    assert cleared["runtime_model_id"] is None
    assert cleared["effective_gp_profile"] == "fast"
    assert cleared["effective_rounds"] == 2


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


def test_update_config_only_rounds_preserves_other_fields(client):  # type: ignore[no-untyped-def]
    client.put("/optimize/config", json={"llm_model": "custom-model", "llm_provider": "ollama"})
    response = client.put("/optimize/config", json={"rounds": 7})
    assert response.status_code == 200
    cfg = response.json()
    assert cfg["runtime_rounds"] == 7
    assert cfg["runtime_llm_model"] == "custom-model"


def test_clear_model_id_with_extra_fields(client):  # type: ignore[no-untyped-def]
    client.put("/optimize/config", json={"model_id": "some-model", "rounds": 3})
    response = client.put(
        "/optimize/config",
        json={"clear_model_id": True, "rounds": 6, "gp_profile": "quality"},
    )
    assert response.status_code == 200
    cfg = response.json()
    assert cfg["runtime_model_id"] is None
    assert cfg["effective_rounds"] == 6
    assert cfg["effective_gp_profile"] == "quality"


def test_update_config_invalid_gp_profile_falls_back_to_fast(client):  # type: ignore[no-untyped-def]
    """Unknown profile names are normalised to 'fast' by the service layer."""
    response = client.put("/optimize/config", json={"gp_profile": "turbo"})
    assert response.status_code == 200
    assert response.json()["effective_gp_profile"] == "fast"


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
        "effective_gp_profile",
        "effective_llm_provider",
        "effective_llm_model",
        "effective_llm_base_url",
        "effective_llm_timeout_seconds",
        "effective_rounds",
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
        "main.list_available_llm_models",
        return_value=["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
    ) as mock_list:
        response = client.get(
            "/optimize/providers/openai/models",
            params={"api_token": "test-token", "timeout_seconds": 5},
        )
    assert response.status_code == 200
    models = response.json()
    assert "gpt-4o" in models
    mock_list.assert_called_once_with(
        "openai",
        base_url=None,
        timeout_seconds=5,
        api_token="test-token",
    )


def test_get_provider_models_case_insensitive_provider(client):  # type: ignore[no-untyped-def]
    """Provider name normalisation — 'ANTHROPIC' should work the same as 'anthropic'."""
    upper = client.get("/optimize/providers/ANTHROPIC/models")
    lower = client.get("/optimize/providers/anthropic/models")
    assert upper.status_code == 200
    assert lower.status_code == 200
    assert upper.json() == lower.json()
