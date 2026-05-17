import base64
import hashlib
import json
import os
import re
from urllib import error as urllib_error
from urllib import request as urllib_request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from threading import Lock
from typing import Any

from loguru import logger

_runtime_config_lock = Lock()


@dataclass
class OptimizationResult:
    engine: str
    optimized_fields: dict[str, str | None]
    optimized_markdown: str
    notes: list[str]


class PromptOptimizerBackend(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def optimize(self, fields: dict[str, str | None], config: dict[str, Any]) -> OptimizationResult:
        raise NotImplementedError

    @abstractmethod
    def list_models(
        self,
        provider: str,
        *,
        base_url: str | None = None,
        timeout_seconds: int = 5,
        api_token: str | None = None,
        config_override: dict[str, Any] | None = None,
    ) -> list[str]:
        raise NotImplementedError


# Token encryption utilities

def _get_encryption_key() -> bytes:
    machine_id = os.getenv("PROMPTMAN_KEY", os.uname().nodename if hasattr(os, "uname") else "default")
    key_material = hashlib.sha256(machine_id.encode()).digest()
    return base64.urlsafe_b64encode(key_material)


def _encrypt_token(token: str | None) -> str | None:
    if not token or not token.strip():
        return None
    try:
        from cryptography.fernet import Fernet

        cipher = Fernet(_get_encryption_key())
        encrypted = cipher.encrypt(token.strip().encode())
        return encrypted.decode("utf-8")
    except Exception as exc:
        logger.warning("Token encryption failed: {}", exc)
        return None


def _decrypt_token(encrypted_token: str | None) -> str | None:
    if not encrypted_token:
        return None
    try:
        from cryptography.fernet import Fernet

        cipher = Fernet(_get_encryption_key())
        decrypted = cipher.decrypt(encrypted_token.encode())
        return decrypted.decode("utf-8")
    except Exception as exc:
        logger.warning("Token decryption failed: {}", exc)
        return None


_runtime_optimize_config: dict[str, Any] = {
    "llm_provider": "openai",
    "llm_model": "gpt-4o-mini",
    "llm_base_url": "",
    "llm_timeout_seconds": 120,
    "llm_api_token_encrypted": None,
}


def build_optimizer_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    if overrides is None:
        with _runtime_config_lock:
            source = dict(_runtime_optimize_config)
    else:
        source = overrides

    runtime_provider = source.get("llm_provider", source.get("runtime_llm_provider"))
    runtime_model = source.get("llm_model", source.get("runtime_llm_model"))
    runtime_base_url = source.get("llm_base_url", source.get("runtime_llm_base_url"))
    runtime_timeout_seconds = source.get("llm_timeout_seconds", source.get("runtime_llm_timeout_seconds"))
    runtime_api_token = source.get("llm_api_token", source.get("effective_llm_api_token"))
    runtime_api_token_encrypted = source.get("llm_api_token_encrypted")

    env_provider = os.getenv("OPTIMIZER_PROVIDER", os.getenv("OPTIMIZE_LLM_PROVIDER", "")).strip().lower() or None
    env_model = os.getenv("OPTIMIZER_MODEL", os.getenv("OPTIMIZE_LLM_MODEL", "")).strip() or None
    env_base_url = os.getenv("OPTIMIZER_BASE_URL", os.getenv("OLLAMA_BASE_URL", "")).strip() or None
    env_api_token_encrypted = os.getenv("OPTIMIZER_API_TOKEN", os.getenv("OPTIMIZE_LLM_API_TOKEN", "")).strip() or None
    env_timeout_raw = os.getenv("OPTIMIZER_TIMEOUT_SECONDS", os.getenv("OPTIMIZE_LLM_TIMEOUT_SECONDS", "")).strip()
    env_timeout_seconds = int(env_timeout_raw) if env_timeout_raw.isdigit() else None

    effective_provider = (runtime_provider or env_provider or "openai").strip().lower()
    default_model_by_provider = {
        "ollama": "qwen2.5:0.5b",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-haiku",
        "groq": "llama3-8b-8192",
        "gemini": "gemini-1.5-flash",
        "mistral": "mistral-small-latest",
    }
    effective_model = (runtime_model or env_model or default_model_by_provider.get(effective_provider, "gpt-4o-mini")).strip()
    effective_base_url = (runtime_base_url or env_base_url or "").strip()
    effective_timeout_seconds = int(runtime_timeout_seconds or env_timeout_seconds or 120)
    effective_api_token = runtime_api_token or _decrypt_token(runtime_api_token_encrypted or env_api_token_encrypted)

    return {
        "runtime_llm_provider": runtime_provider,
        "runtime_llm_model": runtime_model,
        "runtime_llm_base_url": runtime_base_url,
        "runtime_llm_timeout_seconds": runtime_timeout_seconds,
        "runtime_has_llm_api_token": runtime_api_token_encrypted is not None,
        "env_llm_provider": env_provider,
        "env_llm_model": env_model,
        "env_llm_base_url": env_base_url,
        "env_llm_timeout_seconds": env_timeout_seconds,
        "env_has_llm_api_token": env_api_token_encrypted is not None,
        "effective_llm_provider": effective_provider,
        "effective_llm_model": effective_model,
        "effective_llm_base_url": effective_base_url,
        "effective_llm_timeout_seconds": effective_timeout_seconds,
        "effective_has_llm_api_token": effective_api_token is not None,
        "effective_llm_api_token": effective_api_token,
    }


def set_runtime_optimizer_config(
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_base_url: str | None = None,
    llm_timeout_seconds: int | None = None,
    llm_api_token: str | None = None,
) -> dict[str, Any]:
    with _runtime_config_lock:
        if llm_provider is not None:
            _runtime_optimize_config["llm_provider"] = llm_provider.strip().lower() or "openai"
        if llm_model is not None:
            _runtime_optimize_config["llm_model"] = llm_model.strip() or "gpt-4o-mini"
        if llm_base_url is not None:
            _runtime_optimize_config["llm_base_url"] = llm_base_url.strip()
        if llm_timeout_seconds is not None:
            _runtime_optimize_config["llm_timeout_seconds"] = max(5, int(llm_timeout_seconds))
        if llm_api_token is not None:
            _runtime_optimize_config["llm_api_token_encrypted"] = _encrypt_token(llm_api_token)

    logger.info(
        "optimize.config.runtime_set provider={} model={} base_url={} timeout_s={} has_api_token={}",
        _runtime_optimize_config.get("llm_provider"),
        _runtime_optimize_config.get("llm_model"),
        _runtime_optimize_config.get("llm_base_url"),
        _runtime_optimize_config.get("llm_timeout_seconds"),
        bool(llm_api_token and llm_api_token.strip()),
    )
    return get_runtime_optimizer_config()


def get_runtime_optimizer_config() -> dict[str, Any]:
    with _runtime_config_lock:
        return build_optimizer_config(dict(_runtime_optimize_config))


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw = value
    elif isinstance(value, (dict, list)):
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

    if optimized["task"] and not optimized["task"].rstrip().endswith((".", "?", "!")):
        optimized["task"] = optimized["task"].rstrip() + "."

    return optimized


def _extract_prefixed_section(text: str, key: str) -> str | None:
    pattern = re.compile(rf"(?im)^\s*{re.escape(key)}\s*:\s*(.+)$")
    match = pattern.search(text)
    if not match:
        return None
    return _normalize_text(match.group(1))


def _parse_structured_response(raw_text: str, fallback: dict[str, str | None]) -> dict[str, str | None]:
    role = _extract_prefixed_section(raw_text, "Role") or fallback.get("role")
    task = _extract_prefixed_section(raw_text, "Task")
    context = _extract_prefixed_section(raw_text, "Context") or fallback.get("context")
    constraints = _extract_prefixed_section(raw_text, "Constraints") or fallback.get("constraints")
    output_format = _extract_prefixed_section(raw_text, "Output format") or fallback.get("output_format")
    examples = _extract_prefixed_section(raw_text, "Examples") or fallback.get("examples")

    if not task:
        task = _normalize_text(raw_text) or fallback.get("task") or ""

    return _heuristic_improve(
        {
            "role": role,
            "task": task,
            "context": context,
            "constraints": constraints,
            "output_format": output_format,
            "examples": examples,
        }
    )


class LeoPromptOptimizerBackend(PromptOptimizerBackend):
    @property
    def name(self) -> str:
        return "leo"

    def _normalize_ollama_base_url(self, base_url: str | None) -> str:
        candidate = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).strip()
        if not candidate:
            candidate = "http://127.0.0.1:11434"
        candidate = candidate.rstrip("/")
        if candidate.endswith("/api"):
            candidate = candidate[:-4]
        if not candidate.endswith("/v1"):
            candidate = f"{candidate}/v1"
        return candidate

    def _looks_like_ollama_base_url(self, base_url: str | None) -> bool:
        if not base_url:
            return False
        candidate = base_url.strip().lower()
        return ":11434" in candidate or "localhost" in candidate or "127.0.0.1" in candidate or "ollama" in candidate

    def _is_ollama_memory_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "requires more system memory" in message or "insufficient memory" in message

    def _pick_low_memory_ollama_model(self, models: list[str], current_model: str) -> str | None:
        preferred = [
            "qwen2.5:0.5b",
            "qwen2.5:1.5b",
            "llama3.2:1b",
            "gemma2:2b",
            "phi3:mini",
        ]

        normalized_current = (current_model or "").strip().lower()
        normalized_models = [m.strip() for m in models if isinstance(m, str) and m.strip()]
        lower_to_original = {m.lower(): m for m in normalized_models}

        for candidate in preferred:
            candidate_lower = candidate.lower()
            if candidate_lower != normalized_current and candidate_lower in lower_to_original:
                return lower_to_original[candidate_lower]

        size_pattern = re.compile(r"(\d+(?:\.\d+)?)b")
        sized: list[tuple[float, str]] = []
        for model in normalized_models:
            match = size_pattern.search(model.lower())
            if match:
                sized.append((float(match.group(1)), model))

        sized.sort(key=lambda item: item[0])
        for _, model in sized:
            if model.lower() != normalized_current:
                return model

        return None

    def _build_provider(self, provider_name: str, api_token: str | None, base_url: str | None):
        from leo_prompt_optimizer import (
            AnthropicProvider,
            GeminiProvider,
            GroqProvider,
            MistralProvider,
            OpenAIProvider,
        )

        normalized = (provider_name or "openai").strip().lower()
        if normalized == "openai":
            if self._looks_like_ollama_base_url(base_url):
                key = (api_token or "ollama").strip() or "ollama"
                url = self._normalize_ollama_base_url(base_url)
                return OpenAIProvider(api_key=key, base_url=url), "openai-compat-ollama"

            key = (api_token or "").strip() or None
            url = (base_url or "").strip() or None
            return OpenAIProvider(api_key=key, base_url=url), "openai"
        if normalized == "ollama":
            key = (api_token or "ollama").strip() or "ollama"
            url = self._normalize_ollama_base_url(base_url)
            return OpenAIProvider(api_key=key, base_url=url), "ollama"
        if normalized == "anthropic":
            return AnthropicProvider(api_key=api_token), "anthropic"
        if normalized == "groq":
            return GroqProvider(api_key=api_token), "groq"
        if normalized == "gemini":
            return GeminiProvider(api_key=api_token), "gemini"
        if normalized == "mistral":
            return MistralProvider(api_key=api_token), "mistral"

        raise ValueError(f"Unsupported provider: {normalized}")

    def optimize(self, fields: dict[str, str | None], config: dict[str, Any]) -> OptimizationResult:
        from leo_prompt_optimizer import LeoOptimizer

        provider_name = config["effective_llm_provider"]
        model_name = config["effective_llm_model"]
        base_url = config.get("effective_llm_base_url")
        api_token = config.get("effective_llm_api_token")

        sanitized = {
            "role": _normalize_text(fields.get("role")),
            "task": _normalize_text(fields.get("task")) or "",
            "context": _normalize_text(fields.get("context")),
            "constraints": _normalize_text(fields.get("constraints")),
            "output_format": _normalize_text(fields.get("output_format")),
            "examples": _normalize_text(fields.get("examples")),
        }

        logger.info("optimize.backend.start backend={} provider={} model={}", self.name, provider_name, model_name)

        try:
            provider, resolved_provider = self._build_provider(provider_name, api_token, base_url)
            optimizer = LeoOptimizer(provider=provider, default_model=model_name)
            raw_result = optimizer.optimize(
                prompt_draft=_build_full_prompt(sanitized),
                top_instruction=(
                    "Optimize this prompt for clarity and reliability. "
                    "Prefer preserving structure with fields Role/Task/Context/Constraints/Output format/Examples."
                ),
                model=model_name,
            )
            parsed = _parse_structured_response(raw_result or "", sanitized)
            return OptimizationResult(
                engine=f"{self.name}-{resolved_provider}:{model_name}",
                optimized_fields=parsed,
                optimized_markdown=_build_full_prompt(parsed),
                notes=[
                    "Optimized with active backend.",
                    f"Backend: {self.name}",
                    f"Provider: {resolved_provider}",
                    f"Model: {model_name}",
                ],
            )
        except Exception as exc:
            if (provider_name or "").strip().lower() == "ollama" and self._is_ollama_memory_error(exc):
                available_models = self.list_models(
                    "ollama",
                    base_url=base_url,
                    timeout_seconds=max(5, int(config.get("effective_llm_timeout_seconds") or 5)),
                    api_token=api_token,
                    config_override=config,
                )
                low_memory_model = self._pick_low_memory_ollama_model(available_models, model_name)
                if low_memory_model:
                    try:
                        logger.warning(
                            "optimize.backend.retry_low_memory provider={} from_model={} to_model={}",
                            provider_name,
                            model_name,
                            low_memory_model,
                        )
                        retry_provider, resolved_provider = self._build_provider(provider_name, api_token, base_url)
                        retry_optimizer = LeoOptimizer(provider=retry_provider, default_model=low_memory_model)
                        retry_raw_result = retry_optimizer.optimize(
                            prompt_draft=_build_full_prompt(sanitized),
                            top_instruction=(
                                "Optimize this prompt for clarity and reliability. "
                                "Prefer preserving structure with fields Role/Task/Context/Constraints/Output format/Examples."
                            ),
                            model=low_memory_model,
                        )
                        retry_parsed = _parse_structured_response(retry_raw_result or "", sanitized)
                        return OptimizationResult(
                            engine=f"{self.name}-{resolved_provider}:{low_memory_model}",
                            optimized_fields=retry_parsed,
                            optimized_markdown=_build_full_prompt(retry_parsed),
                            notes=[
                                "Optimized with active backend.",
                                f"Backend: {self.name}",
                                f"Provider: {resolved_provider}",
                                f"Model: {low_memory_model}",
                                f"Switched from {model_name} due to memory constraints.",
                            ],
                        )
                    except Exception as retry_exc:
                        exc = RuntimeError(f"{exc}; retry_with_low_memory_model_failed: {retry_exc}")

            logger.exception("optimize.backend.error backend={} provider={} model={}", self.name, provider_name, model_name)
            fallback = _heuristic_improve(sanitized)
            return OptimizationResult(
                engine=f"{self.name}-fallback",
                optimized_fields=fallback,
                optimized_markdown=_build_full_prompt(fallback),
                notes=[
                    f"Backend optimization failed: {exc}",
                    "Fallback optimization was used.",
                ],
            )

    def list_models(
        self,
        provider: str,
        *,
        base_url: str | None = None,
        timeout_seconds: int = 5,
        api_token: str | None = None,
        config_override: dict[str, Any] | None = None,
    ) -> list[str]:
        normalized = (provider or "").strip().lower()
        if normalized == "openai" and self._looks_like_ollama_base_url(base_url):
            normalized = "ollama"

        if normalized == "ollama":
            configured_base_url = (base_url or "").strip()
            if not configured_base_url and config_override:
                configured_base_url = (config_override.get("effective_llm_base_url") or "").strip()
            if not configured_base_url:
                configured_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()

            normalized_openai_base = self._normalize_ollama_base_url(configured_base_url)
            service_base = normalized_openai_base[:-3] if normalized_openai_base.endswith("/v1") else normalized_openai_base
            tags_url = f"{service_base.rstrip('/')}/api/tags"
            try:
                with urllib_request.urlopen(tags_url, timeout=timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                models = payload.get("models") if isinstance(payload, dict) else []
                names = []
                for model in models or []:
                    if isinstance(model, dict):
                        name = (model.get("name") or "").strip()
                        if name:
                            names.append(name)
                return sorted(set(names))
            except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, json.JSONDecodeError):
                return []

        if normalized == "openai":
            if not (api_token or "").strip():
                return []
            return ["gpt-4o", "gpt-4o-mini", "gpt-4.1-mini"]
        if normalized == "anthropic":
            return ["claude-3-5-sonnet", "claude-3-haiku"]
        if normalized == "groq":
            return ["llama-3.3-70b-versatile", "llama3-8b-8192"]
        if normalized == "gemini":
            return ["gemini-1.5-pro", "gemini-1.5-flash"]
        if normalized == "mistral":
            return ["mistral-large-latest", "mistral-small-latest"]
        return []


_BACKEND_REGISTRY: dict[str, PromptOptimizerBackend] = {
    "leo": LeoPromptOptimizerBackend(),
}


def get_active_optimizer_backend_name() -> str:
    configured = os.getenv("OPTIMIZER_BACKEND", "leo").strip().lower() or "leo"
    if configured not in _BACKEND_REGISTRY:
        logger.warning("optimize.backend.unknown configured={} fallback=leo", configured)
        return "leo"
    return configured


def get_active_optimizer_backend() -> PromptOptimizerBackend:
    return _BACKEND_REGISTRY[get_active_optimizer_backend_name()]


def optimize_prompt_with_active_backend(fields: dict[str, str | None], config_override: dict[str, Any] | None = None) -> OptimizationResult:
    backend = get_active_optimizer_backend()
    config = build_optimizer_config(config_override)
    return backend.optimize(fields, config)


def list_available_models(
    provider: str,
    *,
    base_url: str | None = None,
    timeout_seconds: int = 5,
    api_token: str | None = None,
    config_override: dict[str, Any] | None = None,
) -> list[str]:
    backend = get_active_optimizer_backend()
    return backend.list_models(
        provider,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        api_token=api_token,
        config_override=config_override,
    )
