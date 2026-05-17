from fastapi.testclient import TestClient


def login_as(client: TestClient, username: str, password: str) -> str:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_auth_status_reports_existing_default_admin(client):  # type: ignore[no-untyped-def]
    response = client.get("/auth/status")
    assert response.status_code == 200
    assert response.json() == {"bootstrap_required": False, "has_users": True}


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
    assert response.json() == [{"id": 1, "name": "admin"}, {"id": 2, "name": "developer"}]


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