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
