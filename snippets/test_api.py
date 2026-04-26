
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

def test_optimize_config():  # type: ignore[no-untyped-def]
    payload = {"gp_profile": "quality", "rounds": 3}
    put_response = client.put("/optimize/config", json=payload)
    assert put_response.status_code == 200, f"PUT failed: {put_response.text}"

    get_response = client.get("/optimize/config")
    assert get_response.status_code == 200, f"GET failed: {get_response.text}"

    data = get_response.json()

    effective_gp_profile = data.get("effective_gp_profile")
    runtime_gp_profile = data.get("runtime_gp_profile")
    effective_rounds = data.get("effective_rounds")
    candidates_topk = data.get("effective_gp_optimize_config", {}).get("candidates_topk")

    print(f"effective_gp_profile: {effective_gp_profile}")
    print(f"runtime_gp_profile: {runtime_gp_profile}")
    print(f"effective_rounds: {effective_rounds}")
    print(f"candidates_topk: {candidates_topk}")

    if (effective_gp_profile == "quality" and
        runtime_gp_profile == "quality" and
        effective_rounds == 3 and
        candidates_topk == 8):
        print("PASS")
    else:
        print("FAIL")

if __name__ == "__main__":
    test_optimize_config()
