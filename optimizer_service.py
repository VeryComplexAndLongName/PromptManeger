import json
import os
from dataclasses import dataclass
from threading import Lock
from typing import Any

import requests
from loguru import logger

_runtime_config_lock = Lock()
_ALLOWED_GP_PROFILES = {"fast", "quality"}
_GREATERPROMPT_PROFILE_CONFIGS: dict[str, dict[str, Any]] = {
    "fast": {
        "generate_config": {
            "max_new_tokens": 160,
            "temperature": 0.25,
            "top_p": 0.9,
            "repetition_penalty": 1.05,
            "no_repeat_ngram_size": 2,
            "do_sample": True,
        },
        "candidates_topk": 4,
        "intersect_q": 1,
        "filter": False,
        "p_extractor": "Answer:",
    },
    "quality": {
        "generate_config": {
            "max_new_tokens": 220,
            "temperature": 0.35,
            "top_p": 0.9,
            "repetition_penalty": 1.1,
            "no_repeat_ngram_size": 3,
            "do_sample": True,
        },
        "candidates_topk": 8,
        "intersect_q": 2,
        "filter": True,
        "p_extractor": "Answer:",
    },
}
_runtime_optimize_config: dict[str, Any] = {
    "model_id": None,
    "rounds": None,
    "gp_profile": "fast",
    "llm_provider": "ollama",
    "llm_model": "qwen2.5:0.5b",
    "llm_base_url": "http://127.0.0.1:11434",
    "llm_timeout_seconds": 300,
}


def _normalize_gp_profile(value: str | None) -> str:
    candidate = (value or "").strip().lower()
    if candidate in _ALLOWED_GP_PROFILES:
        return candidate
    return "fast"


def _get_gp_optimize_config(profile: str) -> dict[str, Any]:
    normalized = _normalize_gp_profile(profile)
    # Deep copy via JSON to avoid accidental mutation across requests.
    result = json.loads(json.dumps(_GREATERPROMPT_PROFILE_CONFIGS[normalized]))
    return result if isinstance(result, dict) else {}


def set_runtime_optimizer_config(
    model_id: str | None = None,
    rounds: int | None = None,
    gp_profile: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_base_url: str | None = None,
    llm_timeout_seconds: int | None = None,
) -> dict[str, Any]:
    with _runtime_config_lock:
        if model_id is not None:
            normalized_model = model_id.strip()
            _runtime_optimize_config["model_id"] = normalized_model or None
        if rounds is not None:
            _runtime_optimize_config["rounds"] = max(1, int(rounds))
        if gp_profile is not None:
            _runtime_optimize_config["gp_profile"] = _normalize_gp_profile(gp_profile)
        if llm_provider is not None:
            _runtime_optimize_config["llm_provider"] = llm_provider.strip().lower() or "ollama"
        if llm_model is not None:
            _runtime_optimize_config["llm_model"] = llm_model.strip() or "qwen2.5:0.5b"
        if llm_base_url is not None:
            _runtime_optimize_config["llm_base_url"] = llm_base_url.strip() or "http://127.0.0.1:11434"
        if llm_timeout_seconds is not None:
            _runtime_optimize_config["llm_timeout_seconds"] = max(5, int(llm_timeout_seconds))
    logger.info(
        "optimize.config.runtime_set model_id={} rounds={} gp_profile={} llm_provider={} llm_model={} llm_base_url={} llm_timeout_seconds={}",
        model_id,
        rounds,
        gp_profile,
        llm_provider,
        llm_model,
        llm_base_url,
        llm_timeout_seconds,
    )
    return get_runtime_optimizer_config()


def clear_runtime_model_id() -> dict[str, Any]:
    with _runtime_config_lock:
        _runtime_optimize_config["model_id"] = None
    logger.info("optimize.config.runtime_clear_model_id")
    return get_runtime_optimizer_config()


def get_runtime_optimizer_config() -> dict[str, Any]:
    with _runtime_config_lock:
        runtime_model_id = _runtime_optimize_config["model_id"]
        runtime_rounds = _runtime_optimize_config["rounds"]
        runtime_gp_profile = _runtime_optimize_config["gp_profile"]
        runtime_llm_provider = _runtime_optimize_config["llm_provider"]
        runtime_llm_model = _runtime_optimize_config["llm_model"]
        runtime_llm_base_url = _runtime_optimize_config["llm_base_url"]
        runtime_llm_timeout_seconds = _runtime_optimize_config["llm_timeout_seconds"]

    env_model_id = os.getenv("GREATERPROMPT_MODEL_ID", "").strip() or None
    env_rounds_raw = os.getenv("GREATERPROMPT_ROUNDS", "").strip()
    env_rounds = int(env_rounds_raw) if env_rounds_raw.isdigit() else None
    env_gp_profile_raw = os.getenv("GREATERPROMPT_PROFILE", "").strip().lower()
    env_gp_profile = _normalize_gp_profile(env_gp_profile_raw) if env_gp_profile_raw else None
    env_llm_provider = os.getenv("OPTIMIZE_LLM_PROVIDER", "").strip().lower() or None
    env_llm_model = os.getenv("OPTIMIZE_LLM_MODEL", "").strip() or None
    env_llm_base_url = os.getenv("OLLAMA_BASE_URL", "").strip() or None
    env_llm_timeout_raw = os.getenv("OPTIMIZE_LLM_TIMEOUT_SECONDS", "").strip()
    env_llm_timeout_seconds = int(env_llm_timeout_raw) if env_llm_timeout_raw.isdigit() else None

    effective_model_id = runtime_model_id if runtime_model_id is not None else env_model_id
    effective_rounds = runtime_rounds if runtime_rounds is not None else (env_rounds or 2)
    effective_gp_profile = _normalize_gp_profile(runtime_gp_profile or env_gp_profile or "fast")
    effective_gp_optimize_config = _get_gp_optimize_config(effective_gp_profile)
    effective_llm_provider = runtime_llm_provider or env_llm_provider or "ollama"
    effective_llm_model = runtime_llm_model or env_llm_model or "qwen2.5:0.5b"
    effective_llm_base_url = runtime_llm_base_url or env_llm_base_url or "http://127.0.0.1:11434"
    effective_llm_timeout_seconds = runtime_llm_timeout_seconds or env_llm_timeout_seconds or 300

    return {
        "runtime_model_id": runtime_model_id,
        "runtime_rounds": runtime_rounds,
        "runtime_gp_profile": runtime_gp_profile,
        "runtime_llm_provider": runtime_llm_provider,
        "runtime_llm_model": runtime_llm_model,
        "runtime_llm_base_url": runtime_llm_base_url,
        "runtime_llm_timeout_seconds": runtime_llm_timeout_seconds,
        "env_model_id": env_model_id,
        "env_rounds": env_rounds,
        "env_gp_profile": env_gp_profile,
        "env_llm_provider": env_llm_provider,
        "env_llm_model": env_llm_model,
        "env_llm_base_url": env_llm_base_url,
        "env_llm_timeout_seconds": env_llm_timeout_seconds,
        "effective_model_id": effective_model_id,
        "effective_rounds": effective_rounds,
        "effective_gp_profile": effective_gp_profile,
        "effective_gp_optimize_config": effective_gp_optimize_config,
        "effective_llm_provider": effective_llm_provider,
        "effective_llm_model": effective_llm_model,
        "effective_llm_base_url": effective_llm_base_url,
        "effective_llm_timeout_seconds": effective_llm_timeout_seconds,
        "gradient_enabled": bool(effective_model_id),
    }


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, str):
        raw = value
    elif isinstance(value, (dict, list)):
        # Some LLMs may return nested JSON in fields that should be strings.
        raw = json.dumps(value, ensure_ascii=False)
    else:
        raw = str(value)

    trimmed = " ".join(raw.split())
    return trimmed or None


def _build_full_prompt(fields: dict[str, str | None]) -> str:
    parts: list[str] = []
    if fields.get("role"):
        parts.append(f"Role: {fields['role']}")
    parts.append(f"Task: {fields['task']}")
    if fields.get("context"):
        parts.append(f"Context: {fields['context']}")
    if fields.get("constraints"):
        parts.append(f"Constraints: {fields['constraints']}")
    if fields.get("output_format"):
        parts.append(f"Output format: {fields['output_format']}")
    if fields.get("examples"):
        parts.append(f"Examples: {fields['examples']}")
    return "\n\n".join(parts)


def _heuristic_improve(fields: dict[str, str | None]) -> dict[str, str | None]:
    optimized = {
        "role": _normalize_text(fields.get("role")),
        "task": _normalize_text(fields.get("task")) or "",
        "context": _normalize_text(fields.get("context")),
        "constraints": _normalize_text(fields.get("constraints")),
        "output_format": _normalize_text(fields.get("output_format")),
        "examples": _normalize_text(fields.get("examples")),
    }

    # Ensure task is explicit and actionable.
    if optimized["task"] and not optimized["task"].rstrip().endswith((".", "?", "!")):
        optimized["task"] = optimized["task"].rstrip() + "."

    if optimized["constraints"] and "do not" not in optimized["constraints"].lower():
        optimized["constraints"] = f"Do not violate the following constraints: {optimized['constraints']}"

    if optimized["output_format"] and "format" not in optimized["output_format"].lower():
        optimized["output_format"] = f"Respond in this format: {optimized['output_format']}"

    return optimized


@dataclass
class OptimizationResult:
    engine: str
    optimized_fields: dict[str, str | None]
    optimized_markdown: str
    notes: list[str]


def _try_gradient_optimization(fields: dict[str, str | None]) -> OptimizationResult | None:
    runtime = get_runtime_optimizer_config()
    model_id = runtime["effective_model_id"] or ""
    gp_profile = runtime["effective_gp_profile"]
    gp_optimize_config = dict(runtime["effective_gp_optimize_config"])
    p_extractor = gp_optimize_config.pop("p_extractor", "Answer:")
    if not model_id:
        logger.debug("optimize.gradient.skip reason=no_model_id")
        return None

    try:
        from greaterprompt import GreaterDataloader, GreaterOptimizer
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except Exception:
        return None

    try:
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForCausalLM.from_pretrained(model_id)
        logger.info("optimize.gradient.model_loaded model_id={}", model_id)

        optimizer = GreaterOptimizer(model=model, tokenizer=tokenizer, optimize_config=gp_optimize_config)

        full_prompt = _build_full_prompt(fields)
        answer_target = fields.get("output_format") or "Provide a clear and concise answer."
        inputs = GreaterDataloader(
            custom_inputs=[
                {
                    "id": "local-1",
                    "question": fields["task"],
                    "prompt": full_prompt,
                    "answer": answer_target,
                }
            ]
        )

        rounds = int(runtime["effective_rounds"])
        logger.info(
            "optimize.gradient.start model_id={} profile={} rounds={} candidates_topk={} intersect_q={} filter={} p_extractor={}",
            model_id,
            gp_profile,
            rounds,
            gp_optimize_config.get("candidates_topk"),
            gp_optimize_config.get("intersect_q"),
            gp_optimize_config.get("filter"),
            p_extractor,
        )
        outputs = optimizer.optimize(inputs=inputs, p_extractor=p_extractor, rounds=max(1, rounds))

        candidates = outputs.get(fields["task"], [])
        if not candidates:
            return None

        best_text = str(candidates[0][0]).strip("'\"")
        improved = dict(fields)
        improved["task"] = _normalize_text(best_text) or fields["task"]
        improved = _heuristic_improve(improved)

        return OptimizationResult(
            engine=f"greaterprompt-gradient:{gp_profile}",
            optimized_fields=improved,
            optimized_markdown=_build_full_prompt(improved),
            notes=[
                f"Optimization finished with GreaterPrompt gradient optimizer ({gp_profile} profile).",
                f"Rounds: {max(1, rounds)}",
            ],
        )
    except Exception:
        logger.exception("optimize.gradient.error model_id={}", model_id)
        return None


def optimize_with_greaterprompt(fields: dict[str, str | None]) -> OptimizationResult:
    logger.info("optimize.greaterprompt.service_start")
    sanitized = {
        "role": _normalize_text(fields.get("role")),
        "task": _normalize_text(fields.get("task")) or "",
        "context": _normalize_text(fields.get("context")),
        "constraints": _normalize_text(fields.get("constraints")),
        "output_format": _normalize_text(fields.get("output_format")),
        "examples": _normalize_text(fields.get("examples")),
    }

    gradient_result = _try_gradient_optimization(sanitized)
    if gradient_result is not None:
        logger.info("optimize.greaterprompt.service_done engine=greaterprompt-gradient")
        return gradient_result

    # Lightweight mode still relies on GreaterPrompt utilities while avoiding heavyweight model loading.
    from greaterprompt import GreaterDataloader
    from greaterprompt.utils import clean_string

    full_prompt = _build_full_prompt(sanitized)
    _ = GreaterDataloader(
        custom_inputs=[
            {
                "id": "light-1",
                "question": sanitized["task"] or "Refine the prompt",
                "prompt": full_prompt,
                "answer": sanitized.get("output_format") or "Produce a structured answer.",
            }
        ]
    )

    improved = _heuristic_improve(sanitized)
    scored = clean_string([(_build_full_prompt(improved), 0.0)])
    best_prompt = scored[0][0] if scored else _build_full_prompt(improved)

    notes = [
        "Optimization used GreaterPrompt in lightweight mode.",
        "Set GREATERPROMPT_MODEL_ID (or runtime optimize config) to enable full gradient optimization.",
    ]

    return OptimizationResult(
        engine="greaterprompt-light",
        optimized_fields=improved,
        optimized_markdown=best_prompt,
        notes=notes,
    )


def _to_prompt_fields(raw: dict[str, Any], fallback: dict[str, str | None]) -> dict[str, str | None]:
    return {
        "role": _normalize_text(raw.get("role")) or fallback.get("role"),
        "task": _normalize_text(raw.get("task")) or fallback.get("task") or "",
        "context": _normalize_text(raw.get("context")) or fallback.get("context"),
        "constraints": _normalize_text(raw.get("constraints")) or fallback.get("constraints"),
        "output_format": _normalize_text(raw.get("output_format")) or fallback.get("output_format"),
        "examples": _normalize_text(raw.get("examples")) or fallback.get("examples"),
    }


def _optimize_with_ollama(fields: dict[str, str | None], cfg: dict[str, Any]) -> OptimizationResult:
    model = cfg["effective_llm_model"]
    base_url = cfg["effective_llm_base_url"].rstrip("/")
    timeout_seconds = int(cfg.get("effective_llm_timeout_seconds", 300))
    logger.info("optimize.llm.ollama.start model={} base_url={} timeout_seconds={}", model, base_url, timeout_seconds)

    system_prompt = (
        "You optimize prompts. Rewrite provided prompt fields to be clearer and more actionable. "
        "Return JSON only with keys: role, task, context, constraints, output_format, examples. "
        "Keep the same language as input when possible."
    )

    user_prompt = (
        "Optimize this prompt:\n"
        f"{_build_full_prompt(fields)}\n\n"
        "Rules:\n"
        "- task must be explicit.\n"
        "- keep optional fields optional.\n"
        "- do not invent domain facts.\n"
        "- output strict JSON only."
    )

    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "prompt": f"System: {system_prompt}\n\nUser: {user_prompt}",
        "options": {"temperature": 0.2},
    }

    resp = requests.post(f"{base_url}/api/generate", json=payload, timeout=timeout_seconds)
    resp.raise_for_status()

    body = resp.json()
    raw_response = body.get("response", "{}")
    parsed = json.loads(raw_response)
    if not isinstance(parsed, dict):
        parsed = {}

    improved = _to_prompt_fields(parsed, fields)
    improved = _heuristic_improve(improved)

    return OptimizationResult(
        engine=f"llm-ollama:{model}",
        optimized_fields=improved,
        optimized_markdown=_build_full_prompt(improved),
        notes=["Optimized with Ollama LLM."],
    )


def optimize_with_llm(fields: dict[str, str | None]) -> OptimizationResult:
    cfg = get_runtime_optimizer_config()
    provider = cfg["effective_llm_provider"]
    logger.info(
        "optimize.llm.service_start provider={} model={} base_url={}",
        provider,
        cfg.get("effective_llm_model"),
        cfg.get("effective_llm_base_url"),
    )

    sanitized = {
        "role": _normalize_text(fields.get("role")),
        "task": _normalize_text(fields.get("task")) or "",
        "context": _normalize_text(fields.get("context")),
        "constraints": _normalize_text(fields.get("constraints")),
        "output_format": _normalize_text(fields.get("output_format")),
        "examples": _normalize_text(fields.get("examples")),
    }

    if provider == "ollama":
        try:
            return _optimize_with_ollama(sanitized, cfg)
        except Exception as exc:
            logger.exception("optimize.llm.ollama.error")
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                response_preview = exc.response.text.strip()
                detail = f"HTTP {exc.response.status_code}: {response_preview}"
            else:
                detail = str(exc) or type(exc).__name__
            fallback = _heuristic_improve(sanitized)
            return OptimizationResult(
                engine="llm-fallback",
                optimized_fields=fallback,
                optimized_markdown=_build_full_prompt(fallback),
                notes=[
                    f"LLM optimization failed: {detail}",
                    "Fallback optimization was used.",
                ],
            )

    fallback = _heuristic_improve(sanitized)
    return OptimizationResult(
        engine="llm-fallback",
        optimized_fields=fallback,
        optimized_markdown=_build_full_prompt(fallback),
        notes=[f"Unsupported LLM provider: {provider}", "Fallback optimization was used."],
    )
