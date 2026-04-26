from optimizer_service import OptimizationResult


def test_end_to_end_all_endpoints(client, sample_prompt_payload, monkeypatch):  # type: ignore[no-untyped-def]
    def fake_greaterprompt(fields):  # type: ignore[no-untyped-def]
        optimized = {
            "role": fields.get("role"),
            "task": f"{fields.get('task', '').strip()} (optimized by GP)",
            "context": fields.get("context"),
            "constraints": fields.get("constraints"),
            "output_format": fields.get("output_format"),
            "examples": fields.get("examples"),
        }
        return OptimizationResult(
            engine="greaterprompt-gradient:quality",
            optimized_fields=optimized,
            optimized_markdown="Task: " + optimized["task"],
            notes=["e2e-gp"],
        )

    def fake_llm(fields):  # type: ignore[no-untyped-def]
        optimized = {
            "role": fields.get("role"),
            "task": f"{fields.get('task', '').strip()} (optimized by LLM)",
            "context": fields.get("context"),
            "constraints": fields.get("constraints"),
            "output_format": fields.get("output_format"),
            "examples": fields.get("examples"),
        }
        return OptimizationResult(
            engine="llm-ollama:test",
            optimized_fields=optimized,
            optimized_markdown="Task: " + optimized["task"],
            notes=["e2e-llm"],
        )

    monkeypatch.setattr("main.optimize_with_greaterprompt", fake_greaterprompt)
    monkeypatch.setattr("main.optimize_with_llm", fake_llm)

    # Root and docs
    assert client.get("/").status_code == 200
    assert client.get("/docs").status_code == 200

    # Create and list/get
    assert client.post("/prompts", json=sample_prompt_payload).status_code == 200
    assert client.get("/prompts").status_code == 200
    prompt = client.get("/prompts/payments/checkout-system").json()
    assert prompt["latest_version"] == 1

    # Search both modes
    and_search = client.get(
        "/prompts/search",
        params=[("tags", "system"), ("tags", "production"), ("mode", "and")],
    )
    assert and_search.status_code == 200
    assert len(and_search.json()) == 1

    or_search = client.get(
        "/prompts/search",
        params=[("tags", "missing"), ("tags", "production"), ("mode", "or")],
    )
    assert or_search.status_code == 200
    assert len(or_search.json()) == 1

    # Runtime optimize config endpoints
    put_cfg = client.put(
        "/optimize/config",
        json={
            "gp_profile": "quality",
            "rounds": 3,
            "llm_provider": "ollama",
            "llm_model": "qwen2.5:0.5b",
            "llm_base_url": "http://127.0.0.1:11434",
            "llm_timeout_seconds": 300,
        },
    )
    assert put_cfg.status_code == 200
    assert put_cfg.json()["effective_gp_profile"] == "quality"
    assert client.get("/optimize/config").status_code == 200

    # Optimize with both engines
    gp_opt = client.post("/optimize/greaterprompt", json=sample_prompt_payload)
    assert gp_opt.status_code == 200
    gp_payload = gp_opt.json()["optimized"]
    assert "optimized by GP" in gp_payload["task"]

    llm_opt = client.post("/optimize/llm", json=sample_prompt_payload)
    assert llm_opt.status_code == 200
    llm_payload = llm_opt.json()["optimized"]
    assert "optimized by LLM" in llm_payload["task"]

    # Save optimized prompt as new version
    update_response = client.put("/prompts/payments/checkout-system", json=gp_payload)
    assert update_response.status_code == 200
    assert update_response.json()["version"] == 2

    # Update tags
    tags_response = client.put(
        "/prompts/payments/checkout-system/tags",
        json={"tags": ["optimized", "critical"]},
    )
    assert tags_response.status_code == 200

    # Versions endpoints
    versions = client.get("/prompts/payments/checkout-system/versions")
    assert versions.status_code == 200
    assert len(versions.json()) == 2

    v1 = client.get("/prompts/payments/checkout-system/versions/1")
    assert v1.status_code == 200
    assert v1.json()["version"] == 1
