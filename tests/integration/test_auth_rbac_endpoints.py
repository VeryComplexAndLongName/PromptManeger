import security
from fastapi.testclient import TestClient


def login_as(client: TestClient, username: str, password: str) -> str:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def login_bundle(client: TestClient, username: str, password: str) -> dict:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()


def test_version_endpoint_exposes_semver_string(client):  # type: ignore[no-untyped-def]
    response = client.get("/version")
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "prompt-man"
    version = payload["version"]
    parts = version.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_auth_status_reports_existing_default_admin(client):  # type: ignore[no-untyped-def]
    response = client.get("/auth/status")
    assert response.status_code == 200
    assert response.json() == {"bootstrap_required": False, "has_users": True}


def test_login_returns_refresh_token_and_30_min_access_expiry(client):  # type: ignore[no-untyped-def]
    payload = login_bundle(client, "admin", "admin")

    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["refresh_token"]
    assert payload["access_token_ttl_seconds"] == 30 * 60
    assert payload["refresh_token_ttl_seconds"] == security.REFRESH_TOKEN_TTL_SECONDS
    assert payload["access_token_expires_at"] < payload["refresh_token_expires_at"]


def test_refresh_returns_new_tokens_after_access_token_expires(client, monkeypatch):  # type: ignore[no-untyped-def]
    payload = login_bundle(client, "admin", "admin")
    expired_now = payload["access_token_expires_at"] + 1

    monkeypatch.setattr(security.time, "time", lambda: expired_now)

    me_response = client.get("/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert me_response.status_code == 401

    refresh_response = client.post("/auth/refresh", json={"refresh_token": payload["refresh_token"]})
    assert refresh_response.status_code == 200

    refreshed = refresh_response.json()
    assert refreshed["access_token"] != payload["access_token"]
    assert refreshed["refresh_token"] != payload["refresh_token"]
    assert refreshed["access_token_ttl_seconds"] == 30 * 60


def test_refresh_rejects_invalid_refresh_token(client):  # type: ignore[no-untyped-def]
    response = client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 401


def test_developer_only_sees_allowed_projects(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    create_user_response = client.post(
        "/users",
        json={
            "username": "dev-payments",
            "password": "dev-pass",
            "role": "developer",
            "projects": ["payments"],
            "is_active": True,
        },
    )
    assert create_user_response.status_code == 200

    prompt_a = dict(sample_prompt_payload)
    prompt_b = dict(sample_prompt_payload)
    prompt_b["name"] = "fraud-check"
    prompt_b["project"] = "fraud"
    prompt_b["task"] = "Generate fraud detection rules"

    assert client.post("/prompts", json=prompt_a).status_code == 200
    assert client.post("/prompts", json=prompt_b).status_code == 200

    developer_token = login_as(client, "dev-payments", "dev-pass")
    developer_client = TestClient(client.app)
    developer_client.headers.update({"Authorization": f"Bearer {developer_token}"})

    list_response = developer_client.get("/prompts")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert len(payload) == 1
    assert payload[0]["project"] == "payments"

    forbidden_response = developer_client.get("/prompts", params={"project": "fraud"})
    assert forbidden_response.status_code == 404


def test_user_management_is_admin_only(client):  # type: ignore[no-untyped-def]
    create_user_response = client.post(
        "/users",
        json={
            "username": "dev-only",
            "password": "dev-pass",
            "role": "developer",
            "projects": ["payments"],
            "is_active": True,
        },
    )
    assert create_user_response.status_code == 200

    developer_token = login_as(client, "dev-only", "dev-pass")
    developer_client = TestClient(client.app)
    developer_client.headers.update({"Authorization": f"Bearer {developer_token}"})

    response = developer_client.get("/users")
    assert response.status_code == 403
    assert developer_client.get("/projects").status_code == 403
    assert developer_client.get("/roles").status_code == 403


def test_viewer_can_read_all_prompts_but_not_admin_endpoints(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    assert client.post("/projects", json={"name": "fraud"}).status_code == 200

    prompt_a = dict(sample_prompt_payload)
    prompt_b = dict(sample_prompt_payload)
    prompt_b["name"] = "fraud-check"
    prompt_b["project"] = "fraud"
    prompt_b["task"] = "Generate fraud detection rules"

    assert client.post("/prompts", json=prompt_a).status_code == 200
    assert client.post("/prompts", json=prompt_b).status_code == 200

    create_user_response = client.post(
        "/users",
        json={
            "username": "viewer-all",
            "password": "viewer-pass",
            "role": "viewer",
            "projects": [],
            "is_active": True,
        },
    )
    assert create_user_response.status_code == 200

    viewer_token = login_as(client, "viewer-all", "viewer-pass")
    viewer_client = TestClient(client.app)
    viewer_client.headers.update({"Authorization": f"Bearer {viewer_token}"})

    prompts_response = viewer_client.get("/prompts")
    assert prompts_response.status_code == 200
    assert {item["project"] for item in prompts_response.json()} == {"payments", "fraud"}

    assert viewer_client.get("/users").status_code == 403
    assert viewer_client.get("/projects").status_code == 403
    assert viewer_client.get("/roles").status_code == 403


def test_viewer_is_read_only_across_mutating_endpoints(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    create_user_response = client.post(
        "/users",
        json={
            "username": "viewer-ro",
            "password": "viewer-pass",
            "role": "viewer",
            "projects": [],
            "is_active": True,
        },
    )
    assert create_user_response.status_code == 200

    viewer_token = login_as(client, "viewer-ro", "viewer-pass")
    viewer_client = TestClient(client.app)
    viewer_client.headers.update({"Authorization": f"Bearer {viewer_token}"})

    assert viewer_client.post("/prompts", json=sample_prompt_payload).status_code == 403
    assert viewer_client.put("/prompts/payments/checkout-system", json={"task": "blocked"}).status_code in {403, 404}
    assert viewer_client.put("/prompts/payments/checkout-system/tags", json={"tags": ["blocked"]}).status_code in {403, 404}
    assert viewer_client.delete("/prompts/payments/checkout-system").status_code in {403, 404}
    assert viewer_client.put("/optimize/config", json={"gp_profile": "quality"}).status_code == 403
    assert viewer_client.post("/optimize", json={"task": "Do something"}).status_code == 403
    assert viewer_client.post("/projects", json={"name": "blocked"}).status_code == 403


def test_viewer_can_read_prompt_details_versions_and_search(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    assert client.post("/prompts", json=sample_prompt_payload).status_code == 200
    assert client.put(
        "/prompts/payments/checkout-system",
        json={"task": "Generate checkout validation rules v2"},
    ).status_code == 200

    create_user_response = client.post(
        "/users",
        json={
            "username": "viewer-reader",
            "password": "viewer-pass",
            "role": "viewer",
            "projects": [],
            "is_active": True,
        },
    )
    assert create_user_response.status_code == 200

    viewer_token = login_as(client, "viewer-reader", "viewer-pass")
    viewer_client = TestClient(client.app)
    viewer_client.headers.update({"Authorization": f"Bearer {viewer_token}"})

    get_response = viewer_client.get("/prompts/payments/checkout-system")
    assert get_response.status_code == 200
    assert get_response.json()["created_by_username"] == "admin"
    assert get_response.json()["updated_by_username"] == "admin"

    versions_response = viewer_client.get("/prompts/payments/checkout-system/versions")
    assert versions_response.status_code == 200
    assert len(versions_response.json()) == 2
    assert all(item["created_by_username"] == "admin" for item in versions_response.json())

    version_response = viewer_client.get("/prompts/payments/checkout-system/versions/1")
    assert version_response.status_code == 200
    assert version_response.json()["created_by_username"] == "admin"

    search_response = viewer_client.get("/prompts/search", params=[("tags", "system"), ("mode", "or")])
    assert search_response.status_code == 200
    assert len(search_response.json()) == 1


def test_optimize_config_is_isolated_per_user(client):  # type: ignore[no-untyped-def]
    create_user_response = client.post(
        "/users",
        json={
            "username": "dev-config",
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
            "llm_provider": "openai",
            "llm_model": "gpt-4o",
            "llm_base_url": "https://api.openai.com/v1",
            "llm_timeout_seconds": 12,
        },
    )
    assert admin_update.status_code == 200

    developer_token = login_as(client, "dev-config", "dev-pass")
    developer_client = TestClient(client.app)
    developer_client.headers.update({"Authorization": f"Bearer {developer_token}"})

    developer_get = developer_client.get("/optimize/config")
    assert developer_get.status_code == 200
    assert developer_get.json()["effective_llm_model"] == "qwen2.5:0.5b"

    developer_update = developer_client.put(
        "/optimize/config",
        json={
            "llm_provider": "anthropic",
            "llm_model": "claude-3-haiku",
            "llm_base_url": "https://api.anthropic.com",
            "llm_timeout_seconds": 18,
        },
    )
    assert developer_update.status_code == 200
    assert developer_update.json()["effective_llm_model"] == "claude-3-haiku"

    admin_get = client.get("/optimize/config")
    assert admin_get.status_code == 200
    assert admin_get.json()["effective_llm_model"] == "gpt-4o"


def test_admin_can_manage_projects(client):  # type: ignore[no-untyped-def]
    create_response = client.post("/projects", json={"name": "payments"})
    assert create_response.status_code == 200
    project = create_response.json()

    list_response = client.get("/projects")
    assert list_response.status_code == 200
    assert any(item["name"] == "payments" for item in list_response.json())

    get_response = client.get(f"/projects/{project['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == project

    update_response = client.put(f"/projects/{project['id']}", json={"name": "payments-core"})
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "payments-core"


def test_admin_can_list_roles(client):  # type: ignore[no-untyped-def]
    response = client.get("/roles")
    assert response.status_code == 200
    assert response.json() == [{"id": 1, "name": "admin"}, {"id": 2, "name": "developer"}, {"id": 3, "name": "viewer"}]


def test_deleting_project_cascades_prompts_and_access(client, sample_prompt_payload):  # type: ignore[no-untyped-def]
    project_response = client.post("/projects", json={"name": "payments"})
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    user_response = client.post(
        "/users",
        json={
            "username": "project-dev",
            "password": "dev-pass",
            "role": "developer",
            "projects": ["payments"],
            "is_active": True,
        },
    )
    assert user_response.status_code == 200
    user_id = user_response.json()["id"]

    prompt_response = client.post("/prompts", json=sample_prompt_payload)
    assert prompt_response.status_code == 200

    delete_response = client.delete(f"/projects/{project_id}")
    assert delete_response.status_code == 204

    list_projects_response = client.get("/projects")
    assert list_projects_response.status_code == 200
    assert list_projects_response.json() == []

    get_user_response = client.get(f"/users/{user_id}")
    assert get_user_response.status_code == 200
    assert get_user_response.json()["projects"] == []

    prompts_response = client.get("/prompts")
    assert prompts_response.status_code == 200
    assert prompts_response.json() == []