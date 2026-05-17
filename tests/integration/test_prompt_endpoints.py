import pytest


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


def test_delete_prompt_removes_it_from_list(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    create_response = client.post("/prompts", json=sample_prompt_payload)
    assert create_response.status_code == 200

    delete_response = client.delete("/prompts/payments/checkout-system")
    assert delete_response.status_code == 204

    get_response = client.get("/prompts/payments/checkout-system")
    assert get_response.status_code == 404

    list_response = client.get("/prompts")
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_delete_missing_prompt_returns_not_found(client):  # type: ignore[no-untyped-def]
    delete_response = client.delete("/prompts/payments/missing")
    assert delete_response.status_code == 404


# ---------------------------------------------------------------------------
# POST /prompts — validation edge cases
# ---------------------------------------------------------------------------


def test_create_prompt_missing_task_returns_422(client):  # type: ignore[no-untyped-def]
    response = client.post("/prompts", json={"name": "no-task", "project": "test"})
    assert response.status_code == 422


def test_create_prompt_missing_name_returns_422(client):  # type: ignore[no-untyped-def]
    response = client.post("/prompts", json={"project": "test", "task": "Do something"})
    assert response.status_code == 422


def test_create_prompt_missing_project_returns_422(client):  # type: ignore[no-untyped-def]
    response = client.post("/prompts", json={"name": "some-prompt", "task": "Do something"})
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [("name", ""), ("name", "   "), ("project", ""), ("project", "   ")],
)
def test_create_prompt_blank_name_or_project_returns_422(client, field_name, field_value):  # type: ignore[no-untyped-def]
    payload = {"name": "some-prompt", "project": "test", "task": "Do something"}
    payload[field_name] = field_value

    response = client.post("/prompts", json=payload)

    assert response.status_code == 422


def test_create_prompt_duplicate_name_returns_400(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    client.post("/prompts", json=sample_prompt_payload)
    response = client.post("/prompts", json=sample_prompt_payload)
    assert response.status_code == 400
    assert "already exists" in response.text


def test_create_prompt_empty_optional_fields_accepted(client):  # type: ignore[no-untyped-def]
    response = client.post(
        "/prompts",
        json={"name": "minimal", "project": "test", "task": "Do something"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "minimal"
    assert body["latest_version"] == 1


# ---------------------------------------------------------------------------
# GET /prompts/{project}/{name} — not found
# ---------------------------------------------------------------------------


def test_get_prompt_not_found(client):  # type: ignore[no-untyped-def]
    response = client.get("/prompts/unknown/no-prompt")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PUT /prompts/{project}/{name} — edge cases
# ---------------------------------------------------------------------------


def test_update_prompt_not_found_returns_404(client):  # type: ignore[no-untyped-def]
    response = client.put("/prompts/unknown/no-prompt", json={"task": "something"})
    assert response.status_code == 404


def test_update_prompt_missing_task_returns_422(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    client.post("/prompts", json=sample_prompt_payload)
    response = client.put("/prompts/payments/checkout-system", json={"role": "New role"})
    assert response.status_code == 422


def test_update_prompt_identical_content_returns_same_version(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    """Submitting identical content to the latest version does not create a new version."""
    client.post("/prompts", json=sample_prompt_payload)
    same_content = {
        "role": sample_prompt_payload["role"],
        "task": sample_prompt_payload["task"],
        "context": sample_prompt_payload["context"],
        "constraints": sample_prompt_payload["constraints"],
        "output_format": sample_prompt_payload["output_format"],
        "examples": sample_prompt_payload["examples"],
    }
    response = client.put("/prompts/payments/checkout-system", json=same_content)
    assert response.status_code == 200
    assert response.json()["version"] == 1  # No new version created


def test_update_prompt_content_matching_another_prompt_returns_409(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    """Content that already exists as any other prompt version raises 409."""
    client.post("/prompts", json=sample_prompt_payload)
    # Create a second prompt with different initial content
    other = {**sample_prompt_payload, "name": "other-prompt", "task": "Unique task for other"}
    client.post("/prompts", json=other)
    # Update other-prompt with content that already exists in checkout-system
    conflict_content = {
        "role": sample_prompt_payload["role"],
        "task": sample_prompt_payload["task"],
        "context": sample_prompt_payload["context"],
        "constraints": sample_prompt_payload["constraints"],
        "output_format": sample_prompt_payload["output_format"],
        "examples": sample_prompt_payload["examples"],
    }
    response = client.put("/prompts/payments/other-prompt", json=conflict_content)
    assert response.status_code == 409


def test_update_prompt_tags_via_put_updates_them(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    client.post("/prompts", json=sample_prompt_payload)
    response = client.put(
        "/prompts/payments/checkout-system",
        json={"task": "Updated task", "tags": ["new-tag"]},
    )
    assert response.status_code == 200
    assert response.json()["version"] == 2


# ---------------------------------------------------------------------------
# PUT /prompts/{project}/{name}/tags — edge cases
# ---------------------------------------------------------------------------


def test_update_prompt_tags_not_found_returns_404(client):  # type: ignore[no-untyped-def]
    response = client.put("/prompts/unknown/no-prompt/tags", json={"tags": ["x"]})
    assert response.status_code == 404


def test_update_prompt_tags_clears_to_empty(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    client.post("/prompts", json=sample_prompt_payload)
    response = client.put("/prompts/payments/checkout-system/tags", json={"tags": []})
    assert response.status_code == 200
    assert response.json()["tags"] == []


def test_update_prompt_tags_deduplicates(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    client.post("/prompts", json=sample_prompt_payload)
    response = client.put(
        "/prompts/payments/checkout-system/tags",
        json={"tags": ["alpha", "Alpha", "ALPHA"]},
    )
    assert response.status_code == 200
    assert response.json()["tags"] == ["alpha"]


# ---------------------------------------------------------------------------
# GET /prompts/{project}/{name}/versions — edge cases
# ---------------------------------------------------------------------------


def test_list_versions_not_found_returns_404(client):  # type: ignore[no-untyped-def]
    response = client.get("/prompts/unknown/no-prompt/versions")
    assert response.status_code == 404


def test_get_specific_version_prompt_not_found(client):  # type: ignore[no-untyped-def]
    response = client.get("/prompts/unknown/no-prompt/versions/1")
    assert response.status_code == 404


def test_get_specific_version_not_found(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    client.post("/prompts", json=sample_prompt_payload)
    response = client.get("/prompts/payments/checkout-system/versions/999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /prompts — filtering and pagination edge cases
# ---------------------------------------------------------------------------


def test_list_prompts_filter_by_project(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    client.post("/prompts", json=sample_prompt_payload)
    client.post(
        "/prompts",
        json={**sample_prompt_payload, "name": "other-prompt", "project": "other", "task": "Other task"},
    )
    response = client.get("/prompts", params={"project": "payments"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["project"] == "payments"


def test_list_prompts_filter_by_tag(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    client.post("/prompts", json=sample_prompt_payload)
    client.post(
        "/prompts",
        json={**sample_prompt_payload, "name": "other-prompt", "task": "Other task", "tags": ["other-tag"]},
    )
    response = client.get("/prompts", params={"tag": "production"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert "production" in data[0]["tags"]


def test_list_prompts_invalid_limit_is_gracefully_ignored(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    client.post("/prompts", json=sample_prompt_payload)
    response = client.get("/prompts", params={"limit": "notanumber"})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_prompts_zero_limit_clamped_to_one(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    for i in range(3):
        client.post(
            "/prompts",
            json={**sample_prompt_payload, "name": f"p{i}", "task": f"task {i}"},
        )
    response = client.get("/prompts", params={"limit": "0"})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_prompts_negative_offset_clamped_to_zero(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    client.post("/prompts", json=sample_prompt_payload)
    response = client.get("/prompts", params={"offset": "-99"})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_list_prompts_returns_x_total_count_header(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    for i in range(4):
        client.post(
            "/prompts",
            json={**sample_prompt_payload, "name": f"p{i}", "task": f"task {i}"},
        )
    response = client.get("/prompts", params={"limit": "2", "offset": "0"})
    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "4"
    assert len(response.json()) == 2


def test_list_prompts_offset_beyond_total_returns_empty(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    client.post("/prompts", json=sample_prompt_payload)
    response = client.get("/prompts", params={"offset": "100"})
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# GET /prompts/search — edge cases
# ---------------------------------------------------------------------------


def test_search_prompts_missing_tags_returns_422(client):  # type: ignore[no-untyped-def]
    response = client.get("/prompts/search")
    assert response.status_code == 422


def test_search_prompts_and_mode_partial_match_returns_empty(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    client.post("/prompts", json=sample_prompt_payload)
    response = client.get(
        "/prompts/search",
        params=[("tags", "system"), ("tags", "nonexistent"), ("mode", "and")],
    )
    assert response.status_code == 200
    assert response.json() == []


def test_search_prompts_or_mode_no_match_returns_empty(client):  # type: ignore[no-untyped-def]
    response = client.get(
        "/prompts/search",
        params=[("tags", "nonexistent"), ("mode", "or")],
    )
    assert response.status_code == 200
    assert response.json() == []


def test_search_prompts_filter_by_project(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    client.post("/prompts", json=sample_prompt_payload)
    client.post(
        "/prompts",
        json={**sample_prompt_payload, "name": "other", "project": "other-proj", "task": "Other task"},
    )
    response = client.get(
        "/prompts/search",
        params=[("tags", "system"), ("project", "payments")],
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["project"] == "payments"


def test_search_prompts_invalid_mode_returns_422(client):  # type: ignore[no-untyped-def]
    response = client.get(
        "/prompts/search",
        params=[("tags", "x"), ("mode", "invalid")],
    )
    assert response.status_code == 422


def test_search_prompts_default_mode_is_or(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    client.post("/prompts", json=sample_prompt_payload)
    # Default mode is "or" — should match on "system" alone
    response = client.get("/prompts/search", params=[("tags", "system")])
    assert response.status_code == 200
    assert len(response.json()) == 1
