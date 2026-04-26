import crud
from optimizer_service import (
    _normalize_text,
    _to_prompt_fields,
    get_runtime_optimizer_config,
    set_runtime_optimizer_config,
)


def test_normalize_tags_deduplicates_and_sorts():  # type: ignore[no-untyped-def]
    tags = [" Prod ", "alpha", "prod", "", "Beta"]

    normalized = crud.normalize_tags(tags)

    assert normalized == ["alpha", "beta", "prod"]


def test_normalize_text_handles_non_string_types():  # type: ignore[no-untyped-def]
    assert _normalize_text({"a": 1}) == '{"a": 1}'
    assert _normalize_text(["x", 2]) == '["x", 2]'
    assert _normalize_text(42) == "42"


def test_to_prompt_fields_falls_back_when_values_missing():  # type: ignore[no-untyped-def]
    raw = {"role": {"nested": "assistant"}, "task": None, "context": ["x", "y"]}
    fallback: dict[str, str | None] = {
        "role": "fallback-role",
        "task": "fallback-task",
        "context": "fallback-context",
        "constraints": "fallback-constraints",
        "output_format": "fallback-output",
        "examples": "fallback-examples",
    }

    result = _to_prompt_fields(raw, fallback)

    assert result["role"] == '{"nested": "assistant"}'
    assert result["task"] == "fallback-task"
    assert result["context"] == '["x", "y"]'
    assert result["constraints"] == "fallback-constraints"


def test_runtime_config_applies_quality_profile():  # type: ignore[no-untyped-def]
    set_runtime_optimizer_config(gp_profile="quality", rounds=3)

    cfg = get_runtime_optimizer_config()

    assert cfg["effective_gp_profile"] == "quality"
    assert cfg["effective_rounds"] == 3
    assert cfg["effective_gp_optimize_config"]["candidates_topk"] == 8
    assert cfg["effective_gp_optimize_config"]["filter"] is True
