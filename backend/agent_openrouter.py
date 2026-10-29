"""OpenRouter transport and usage accounting for the Studio agent."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request

import agent_storage
import credentials
import store


MODEL = "deepseek/deepseek-v4.1-flash-1017"
BASE = "https://openrouter.ai/api/v1"


def model_prices():
    request = urllib.request.Request(BASE + "/models", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.load(response)
        model = next(item for item in data["data"] if item.get("id") == MODEL)
        pricing = model["pricing"]
        prompt, completion = float(pricing["prompt"]), float(pricing["completion"])
        if not all(math.isfinite(price) and price >= 0 for price in (prompt, completion)):
            raise ValueError("Invalid pricing")
        return {"prompt_per_token": prompt, "completion_per_token": completion}
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        raise store.StudioError("Не вдалося отримати поточні ціни OpenRouter.", 503) from None


def estimate(messages, prices, max_output_tokens=4096):
    # Character-based approximation: actual tokenization and provider pricing vary.
    characters = len(json.dumps(messages, ensure_ascii=False))
    approximate_input = max(1, math.ceil(characters / 3))
    amount = approximate_input * prices["prompt_per_token"] + max_output_tokens * prices["completion_per_token"]
    return {"estimated_input_tokens": approximate_input, "max_output_tokens": max_output_tokens, "estimated_usd": amount}


def chat(project_id, messages, tools=None, max_output_tokens=4096, reasoning_effort="auto"):
    if not isinstance(reasoning_effort, str) or reasoning_effort not in agent_storage.REASONING_EFFORTS:
        raise store.StudioError("Невідомий рівень мислення")
    try:
        key = credentials.vault().read(credentials.service_name("openrouter"))
    except RuntimeError:
        raise store.StudioError("Додайте ключ OpenRouter у налаштуваннях студії.", 503) from None
    payload = {"model": MODEL, "messages": messages, "max_tokens": max_output_tokens, "usage": {"include": True}}
    if reasoning_effort != "auto":
        payload["reasoning"] = {"effort": reasoning_effort}
        payload["provider"] = {"require_parameters": True}
    if tools:
        payload["tools"] = tools
    request = urllib.request.Request(BASE + "/chat/completions", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST", headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "Accept": "application/json"})
    amount = None
    request_id = None
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
        request_id = result.get("id")
        raw_amount = result.get("usage", {}).get("cost")
        if type(raw_amount) in (int, float) and math.isfinite(raw_amount) and raw_amount >= 0:
            amount = raw_amount
        message = result["choices"][0]["message"]
        if not isinstance(message, dict):
            raise ValueError("Invalid model response")
        return message
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        raise store.StudioError("OpenRouter не повернув коректну відповідь. Перевірте ключ і доступність сервісу.", 502) from None
    finally:
        agent_storage.add_cost(project_id, "chat", MODEL, amount, request_id)
