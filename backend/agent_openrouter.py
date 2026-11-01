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
