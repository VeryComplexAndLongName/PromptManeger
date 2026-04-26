def test_prompt_crud_search_and_versions(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    create_response = client.post("/prompts", json=sample_prompt_payload)
    assert create_response.status_code == 200

    list_response = client.get("/prompts")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    get_response = client.get("/prompts/payments/checkout-system")
    assert get_response.status_code == 200
    prompt = get_response.json()
    assert prompt["latest_version"] == 1
    assert set(prompt["tags"]) == {"system", "production"}

    search_or = client.get("/prompts/search", params=[("tags", "system"), ("tags", "missing"), ("mode", "or")])
    assert search_or.status_code == 200
    assert len(search_or.json()) == 1

    search_and = client.get("/prompts/search", params=[("tags", "system"), ("tags", "production"), ("mode", "and")])
    assert search_and.status_code == 200
    assert len(search_and.json()) == 1

    update_response = client.put(
        "/prompts/payments/checkout-system",
        json={
            "role": "Updated role",
            "task": "Generate secure checkout validation rules",
            "context": "Target country: US+EU",
            "constraints": "No PII in output",
            "output_format": "JSON",
            "examples": "Input: card=visa, amount=10",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["version"] == 2

    update_tags_response = client.put(
        "/prompts/payments/checkout-system/tags",
        json={"tags": ["critical", "backend"]},
    )
    assert update_tags_response.status_code == 200
    assert set(update_tags_response.json()["tags"]) == {"critical", "backend"}

    versions_response = client.get("/prompts/payments/checkout-system/versions")
    assert versions_response.status_code == 200
    versions = versions_response.json()
    assert len(versions) == 2

    specific_version_response = client.get("/prompts/payments/checkout-system/versions/1")
    assert specific_version_response.status_code == 200
    assert specific_version_response.json()["task"] == sample_prompt_payload["task"]


def test_duplicate_prompt_version_content_returns_conflict(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    first = client.post("/prompts", json=sample_prompt_payload)
    assert first.status_code == 200

    duplicate_prompt = {
        "name": "checkout-system-copy",
        "project": "payments",
        "tags": ["system"],
        "role": sample_prompt_payload["role"],
        "task": sample_prompt_payload["task"],
        "context": sample_prompt_payload["context"],
        "constraints": sample_prompt_payload["constraints"],
        "output_format": sample_prompt_payload["output_format"],
        "examples": sample_prompt_payload["examples"],
    }

    duplicate_create = client.post("/prompts", json=duplicate_prompt)
    assert duplicate_create.status_code == 409
    assert "Duplicate prompt version content" in duplicate_create.text


def test_list_prompts_supports_optional_limit_and_offset(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    for index in range(3):
        payload = {
            **sample_prompt_payload,
            "name": f"checkout-system-{index}",
            "task": f"Generate checkout validation rules {index}",
        }
        response = client.post("/prompts", json=payload)
        assert response.status_code == 200

    full_response = client.get("/prompts")
    assert full_response.status_code == 200
    assert len(full_response.json()) == 3
    assert full_response.headers["X-Total-Count"] == "3"

    paged_response = client.get("/prompts", params={"limit": 2, "offset": 1})
    assert paged_response.status_code == 200
    paged_items = paged_response.json()
    assert len(paged_items) == 2
    assert paged_response.headers["X-Total-Count"] == "3"
    assert paged_items[0]["name"] == "checkout-system-1"
    assert paged_items[1]["name"] == "checkout-system-2"
