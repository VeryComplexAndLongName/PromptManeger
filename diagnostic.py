
import requests


def run_diagnostic():  # type: ignore[no-untyped-def]
    try:
        # 1) GET config
        config_url = "http://127.0.0.1:8000/optimize/config"
        print(f"--- Fetching config from {config_url} ---")
        config_resp = requests.get(config_url)
        config_resp.raise_for_status()
        config = config_resp.json()
        model = config.get("effective_llm_model")
        base_url = config.get("effective_llm_base_url")
        print(f"effective_llm_model: {model}")
        print(f"effective_llm_base_url: {base_url}")

        if not model or not base_url:
            print("Error: Missing model or base_url in config.")
            return

        # 2) Call Ollama tags
        tags_url = f"{base_url.rstrip('/')}/api/tags"
        print(f"\n--- Fetching Ollama tags from {tags_url} ---")
        tags_resp = requests.get(tags_url)
        tags_resp.raise_for_status()
        tags_data = tags_resp.json()
        models = [m['name'] for m in tags_data.get('models', [])]
        print(f"First few models: {models[:5]}")
        exists = model in models or any(model in m for m in models) # Basic check
        print(f"Effective model '{model}' exists: {exists}")

        # 3) Call Ollama generate
        gen_url = f"{base_url.rstrip('/')}/api/generate"
        print(f"\n--- Calling Ollama generate at {gen_url} ---")
        payload = {
            "model": model,
            "prompt": "say ok",
            "stream": False
        }
        gen_resp = requests.post(gen_url, json=payload)
        print(f"Status Code: {gen_resp.status_code}")
        print(f"Response Body: {gen_resp.text}")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    run_diagnostic()
