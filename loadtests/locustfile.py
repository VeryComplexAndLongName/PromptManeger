from __future__ import annotations

import os
import random
import string

from locust import HttpUser, between, task

PROJECT = os.getenv("LOADTEST_PROJECT", "loadtest")
TAGS = ["load", "perf", "prompt"]


def _rand_suffix(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _random_prompt_payload(unique_id: str) -> dict[str, str | None | list[str]]:
    task_value = f"rewrite_prompt_{unique_id}"
    return {
        "name": f"prompt_{unique_id}",
        "project": PROJECT,
        "tags": TAGS,
        "role": "assistant",
        "task": task_value,
        "context": "customer support",
        "constraints": "be concise",
        "output_format": "markdown",
        "examples": "n/a",
    }


class ReadOnlyUser(HttpUser):
    wait_time = between(0.05, 0.4)
    weight = 5

    @task(6)
    def list_prompts(self) -> None:
        self.client.get("/prompts?limit=25&offset=0", name="GET /prompts")

    @task(2)
    def search_by_tag(self) -> None:
        self.client.get("/prompts/search?tags=load&mode=or", name="GET /prompts/search")


class CrudUser(HttpUser):
    wait_time = between(0.1, 0.8)
    weight = 3

    @task(2)
    def create_and_update_prompt(self) -> None:
        uid = _rand_suffix(10)
        payload = _random_prompt_payload(uid)

        create_resp = self.client.post("/prompts", json=payload, name="POST /prompts")
        if create_resp.status_code not in (200, 201):
            return

        update_payload = {
            "role": "assistant",
            "task": f"rewrite_prompt_{uid}_v2",
            "context": "customer support",
            "constraints": "be concise and polite",
            "output_format": "markdown",
            "examples": "n/a",
            "tags": ["load", "perf", "updated"],
        }
        self.client.put(
            f"/prompts/{PROJECT}/prompt_{uid}",
            json=update_payload,
            name="PUT /prompts/{project}/{name}",
        )

    @task(2)
    def read_prompt(self) -> None:
        # Reads are expected to dominate, even for CRUD users.
        self.client.get("/prompts?limit=10&offset=0", name="GET /prompts")


class OptimizeUser(HttpUser):
    wait_time = between(1.0, 3.0)
    weight = int(os.getenv("LOADTEST_OPTIMIZE_WEIGHT", "1"))

    @task(1)
    def optimize_llm(self) -> None:
        payload = {
            "role": "assistant",
            "task": "Rewrite the prompt to improve clarity and structure.",
            "context": "E-commerce support scenario",
            "constraints": "Keep it under 120 words",
            "output_format": "markdown",
            "examples": "none",
        }
        self.client.post("/optimize/llm", json=payload, name="POST /optimize/llm", timeout=120)
