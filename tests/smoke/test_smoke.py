def test_root_serves_ui(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/")

    assert response.status_code == 200
    assert "Prompt Manager" in response.text


def test_docs_available(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/docs")

    assert response.status_code == 200
    assert "swagger" in response.text.lower()
