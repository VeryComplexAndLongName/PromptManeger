
import requests

base_url = 'http://127.0.0.1:8000'

# 1) PUT config
put_resp = requests.put(
    f'{base_url}/optimize/config',
    json={"gp_profile": "quality", "rounds": 3}
)
put_resp.raise_for_status()

# 2) GET config
get_resp = requests.get(f'{base_url}/optimize/config')
get_resp.raise_for_status()
config = get_resp.json()

# 3) Print results
print(f"effective_gp_profile: {config.get('effective_gp_profile')}")
print(f"runtime_gp_profile: {config.get('runtime_gp_profile')}")
print(f"effective_rounds: {config.get('effective_rounds')}")

gp_opt_config = config.get('effective_gp_optimize_config', {})
has_topk_8 = gp_opt_config.get('candidates_topk') == 8
print(f"effective_gp_optimize_config has candidates_topk=8: {has_topk_8}")
