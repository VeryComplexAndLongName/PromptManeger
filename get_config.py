import json

import requests

base_url = "http://127.0.0.1:8000"
try:
    response = requests.get(f"{base_url}/optimize/config")
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
