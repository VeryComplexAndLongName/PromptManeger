# Prompt Man

Local FastAPI + Vue app for storing, versioning, tagging, and optimizing prompt templates.

## Main Purpose Snapshot

![Main Program Purpose](screen2.png)

![Screenshot 1](1.png)
![Screenshot 2](2.png)



## Key Features

- Prompt storage by `project` + `name`
- Immutable prompt version history
- Tagging with AND/OR search
- Prompt deletion with cascading cleanup
- Structured prompt fields:
  - `role` (optional)
  - `task` (required)
  - `context` (optional)
  - `constraints` (optional)
  - `output_format` (optional)
  - `examples` (optional)
- Split optimization actions in UI:
  - default click: `Optimize Prompt` -> GreaterPrompt flow
  - dropdown item: `Optimize Prompt with LLM` -> LLM flow
- Multi-provider LLM support (Ollama, OpenAI, Anthropic)
- Dynamic LLM model discovery from provider
- Runtime optimization tuning without restart via `GET/PUT /optimize/config`:
  - GreaterPrompt: `model_id`, `rounds`, `gp_profile`
  - LLM: `llm_provider`, `llm_model`, `base_url`, `llm_api_token` (encrypted), `llm_timeout_seconds`
- Reoptimize button for in-place optimization modal refinement

## Requirements

- Python 3.11+
- `uv` (recommended) or pip

## Setup

### Using uv (recommended)

```powershell
uv sync --extra dev
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

### Using pip

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
```

## Run

```powershell
uvicorn main:app --reload
```

- UI: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs

## UI Overview

### Browse tab

- Expand prompt card to view latest structured prompt and versions.
- Browse uses server-side pagination.
- The UI requests prompt slices with optional `limit` and `offset`.
- `Optimize Prompt` (main click) runs GreaterPrompt optimization.
- `Optimize Prompt with LLM` (dropdown item) runs LLM optimization.
- Optimization result opens in modal.
- `Update Prompt` in modal saves optimized data as a new version.
- `Delete Prompt` removes the prompt and all its versions (with confirmation).

### Create tab

- Fill prompt metadata (`name`, `project`, `tags`) and `Prompt Data` group box.
- `Optimize Prompt` main click uses GreaterPrompt.
- Dropdown includes `Optimize Prompt with LLM`.
- `Update Prompt` in modal applies optimized values back to Create form.

### Optimization Modal

When optimization completes, a modal shows the result with two sections:

**LLM Settings** (when using LLM optimization):
- **LLM Provider:** Dropdown to switch between Ollama, OpenAI, Anthropic Claude
- **LLM Model:** Dynamically populated based on provider; fetched from provider's model list
- **Base URL:** Auto-updates when provider changes; editable for custom endpoints
- **API Token:** Appears only for OpenAI and Anthropic; masked input for security
  - Shows "✓ Token is configured" if one is already saved
  - Token is encrypted on server, never exposed in API responses
- **LLM Timeout (seconds):** Timeout for LLM API calls

**GreaterPrompt Settings** (always available):
- **GreaterPrompt Profile:** `fast` or `quality` preset
- **GreaterPrompt Model ID (optional):** For gradient-mode optimization
- **Gradient Rounds:** Number of rounds for GreaterPrompt optimization

**Action Buttons:**
- **Save Config:** Persists all settings (including encrypted token) for next session
- **Reoptimize:** Re-runs optimization with current settings without closing modal
- **Update Prompt:** Accepts the result and updates the prompt version

## Optimization Endpoints

### 1) GreaterPrompt optimization

```text
POST /optimize/greaterprompt
```

- Default path behind main `Optimize Prompt` button.
- Uses gradient mode if configured, otherwise lightweight fallback.

### 2) LLM optimization

```text
POST /optimize/llm
```

- Used by `Optimize Prompt with LLM` menu item.
- By default uses local Ollama configuration.

### 3) Runtime optimization config

```text
GET /optimize/config
PUT /optimize/config
```

- Change optimization configuration in runtime, without restarting server.
- Supports both GreaterPrompt and LLM configuration.

Example update (GreaterPrompt + Ollama):

```json
{
  "model_id": null,
  "rounds": 2,
  "gp_profile": "fast",
  "llm_provider": "ollama",
  "llm_model": "qwen2.5:0.5b",
  "llm_base_url": "http://127.0.0.1:11434",
  "llm_timeout_seconds": 300,
  "llm_api_token": null
}
```

Example update (OpenAI with token):

```json
{
  "llm_provider": "openai",
  "llm_model": "gpt-4-turbo",
  "llm_base_url": "https://api.openai.com/v1",
  "llm_api_token": "sk-...",
  "llm_timeout_seconds": 300
}
```

**API Token Security:**
- `llm_api_token` is optional and only required for providers that need authentication (OpenAI, Anthropic)
- Token is encrypted on the server using Fernet encryption with a machine-specific key
- API responses never return the token value, only a boolean flag indicating if one is configured (`effective_has_llm_api_token`)
- Token is only decrypted internally when actually needed for API calls
- Never expose plaintext tokens in logs or responses

`gp_profile` options:

- `fast` (default): lower candidate count and lighter generation for CPU-friendly latency
- `quality`: more candidates + stricter filtering for better output quality with higher cost

When gradient mode is enabled (`model_id` set), the active profile controls GreaterPrompt optimizer internals.

## Optimization Config Recommendations

### Multi-Provider LLM Support

The application supports three LLM providers out of the box:

#### Ollama (Local)

- **Default provider** for local inference
- **Base URL:** `http://127.0.0.1:11434`
- **Authentication:** Not required (no token)
- **Available models:** Dynamically discovered from Ollama `/api/tags`
- **Use case:** Local CPU/GPU inference, no API costs, full privacy

Recommended models:
- CPU-only: `qwen2.5:0.5b`, `llama3.2:1b`, `phi3:mini`
- GPU: `llama3.1:8b`, `qwen2.5:7b`, `gemma2:9b`

#### OpenAI

- **Base URL:** `https://api.openai.com/v1` (or custom endpoint)
- **Authentication:** Required — set `llm_api_token` to your API key
- **Available models:** `gpt-4`, `gpt-4-turbo`, `gpt-3.5-turbo`
- **Use case:** Cloud-based inference, latest models, higher quality

Setup:
1. Get API key from https://platform.openai.com/api-keys
2. In UI: Select **OpenAI** from LLM Provider dropdown
3. Enter API token in **API Token** field
4. Select model
5. Click **Save Config**

#### Anthropic Claude

- **Base URL:** `https://api.anthropic.com` (or custom endpoint)
- **Authentication:** Required — set `llm_api_token` to your API key
- **Available models:** `claude-3-opus`, `claude-3-sonnet`, `claude-3-haiku`
- **Use case:** Alternative cloud provider, strong reasoning capabilities

Setup:
1. Get API key from https://console.anthropic.com/
2. In UI: Select **Anthropic Claude** from LLM Provider dropdown
3. Enter API token in **API Token** field
4. Select model
5. Click **Save Config**

### Default in this project

Current runtime default is configured for local Ollama on CPU-friendly model:

- `llm_provider`: `ollama`
- `llm_model`: `qwen2.5:0.5b`
- `base_url`: `http://127.0.0.1:11434`
- `llm_timeout_seconds`: `300`
- `gp_profile`: `fast`

### If you DO NOT have GPU (CPU-only)

Recommended Ollama models (faster and lighter):

1. `qwen2.5:0.5b` (ultra-light default)
2. `llama3.2:1b` (very light, fast)
3. `phi3:mini` (good quality/speed on CPU)

Tips:

- Keep model size small (1B-3B class) for acceptable latency.
- Expect slower response than GPU, especially for long prompts.
- Prefer LLM optimization mode for practical local usage.
- For gradient mode on CPU, start with:
  - `gp_profile=fast`
  - `rounds=2`

### If you HAVE GPU

Recommended options:

1. Ollama medium models (for better quality):
   - `llama3.1:8b`
   - `qwen2.5:7b`
   - `gemma2:9b`
2. GreaterPrompt gradient mode with supported HF model:
   - set `model_id` (runtime config or `GREATERPROMPT_MODEL_ID`)
   - keep `rounds` in range 2-4 initially

Tips:

- Start with LLM mode for responsiveness, then evaluate gradient mode where needed.
- Watch VRAM usage before increasing model size or rounds.
- For gradient mode on GPU, try:
  - `gp_profile=quality`
  - `rounds=3-5`

### GreaterPrompt Profiles (runtime)

These presets are applied when gradient optimization is enabled.

#### `fast` profile

- `candidates_topk=4`
- `intersect_q=1`
- `filter=false`
- `generate_config`:
  - `max_new_tokens=160`
  - `temperature=0.25`
  - `top_p=0.9`
  - `repetition_penalty=1.05`
  - `no_repeat_ngram_size=2`
  - `do_sample=true`

#### `quality` profile

- `candidates_topk=8`
- `intersect_q=2`
- `filter=true`
- `generate_config`:
  - `max_new_tokens=220`
  - `temperature=0.35`
  - `top_p=0.9`
  - `repetition_penalty=1.1`
  - `no_repeat_ngram_size=3`
  - `do_sample=true`

## Environment Variables

- `DATABASE_URL` (default: `sqlite:///./prompts.db`)
- `GREATERPROMPT_MODEL_ID` (optional fallback for gradient mode)
- `GREATERPROMPT_ROUNDS` (optional fallback, default `2`)
- `GREATERPROMPT_PROFILE` (optional fallback: `fast` or `quality`, default `fast`)
- `OPTIMIZE_LLM_PROVIDER` (optional fallback, default `ollama`)
- `OPTIMIZE_LLM_MODEL` (optional fallback, default `qwen2.5:0.5b`)
- `OLLAMA_BASE_URL` (optional fallback, default `http://127.0.0.1:11434`)
- `OPTIMIZE_LLM_TIMEOUT_SECONDS` (optional fallback, default `300`)
- `OPTIMIZE_LLM_API_TOKEN` (optional encrypted API token for OpenAI/Anthropic)
- `PROMPTMAN_KEY` (optional encryption key for token; if not set, uses machine hostname)

Runtime config from `/optimize/config` has higher priority than env variables for the running process.

## Prompt API (Core)

- `GET /prompts`
  - optional query params:
    - `limit`: max number of prompts to return
    - `offset`: number of prompts to skip
  - when omitted, returns all matching prompts
  - response header `X-Total-Count` contains total number of matching prompts before pagination
- `GET /prompts/search`
- `POST /prompts`
- `GET /prompts/{project}/{name}`
- `PUT /prompts/{project}/{name}`
- `DELETE /prompts/{project}/{name}`
  - Deletes the prompt and all associated versions and tags
  - Returns `204 No Content` on success
  - Returns `404 Not Found` if prompt doesn't exist
- `PUT /prompts/{project}/{name}/tags`
- `GET /prompts/{project}/{name}/versions`
- `GET /prompts/{project}/{name}/versions/{version}`

## Prompt Version Uniqueness

- `prompt_versions` now enforces uniqueness for the full content tuple:
  - `role`, `task`, `context`, `constraints`, `output_format`, `examples`
- API-level protection is also enabled before insert:
  - `POST /prompts` and `PUT /prompts/{project}/{name}` return `409 Conflict`
    when the same content tuple already exists in `prompt_versions`.
- Alembic migration includes a duplicate-data pre-check and stops with a clear error
  if existing duplicates are found. Deduplicate old rows first, then re-run migration.

## Pagination Example

Get all prompts:

```text
GET /prompts
```

Get only part of prompts:

```text
GET /prompts?limit=10&offset=20
```

- `limit` and `offset` are optional.
- This allows API clients to either fetch the full collection or just a page/slice.

## Development

```powershell
ruff check .
ruff format .
mypy .
```

## Load Testing

This project includes repeatable load testing based on Locust and CSV-based chart generation.

### Run benchmark

```powershell
python loadtests/benchmark_rps.py --host http://127.0.0.1:8000 --duration 30s --users 10 20 40 --spawn-rate 10
```

### Build charts

```powershell
python loadtests/generate_charts.py
```

Charts are built from aggregated rows in `loadtests/results/**/u*_stats.csv` and written to `loadtests/`.

### Chart: Dashboard

![Load Testing Dashboard](loadtests/chart_dashboard.png)

Combined view for quick comparison across scenarios and user levels:
- Throughput (`RPS`)
- P95 latency
- Average latency
- Failure rate

### Chart: Throughput (RPS)

![Load Test Throughput](loadtests/chart_rps.png)

Shows how total request throughput changes as concurrent user count increases.
Use this graph to estimate sustainable request rate before latency degradation.

### Chart: P95 Latency

![Load Test P95 Latency](loadtests/chart_p95_latency.png)

Shows tail latency behavior.
If this curve grows sharply, the service is near a bottleneck and user-facing response time becomes unstable.

### Chart: Average Latency

![Load Test Average Latency](loadtests/chart_avg_latency.png)

Shows general response-time trend under load.
Useful with P95 to distinguish overall slowdown from tail-only spikes.

### Chart: Failure Rate

![Load Test Failure Rate](loadtests/chart_failure_rate.png)

Shows percentage of failed requests per run.
Combine this with latency and RPS to define production-ready capacity thresholds.

## Snippets

- Diagnostic one-off scripts are stored in `snippets/`.
- Current files:
  - `snippets/task_snippet.py` - runtime `/optimize/config` verification against running server.
  - `snippets/test_api.py` - local `TestClient` check for optimize config behavior.
  - `snippets/test_snippet.py` - direct helper-function check for non-string field normalization.

## Project Structure

```text
.
├── main.py
├── crud.py
├── models.py
├── schemas.py
├── optimizer_service.py
├── database.py
├── pyproject.toml
├── requirements.txt
├── snippets/
├── tests/
├── alembic/
└── ui/
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
