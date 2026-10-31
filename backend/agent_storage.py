"""Persistent project conversations and per-channel agent preferences."""

from __future__ import annotations

import fcntl
import math
import time
import uuid
from contextlib import contextmanager

import store

REASONING_EFFORTS = {"auto", "low", "high", "max"}


@contextmanager
def locked_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with store.LOCK, path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def conversation_path(project_id):
    return store.project_dir(project_id) / "agent-conversation.json"


def settings_path(project_id):
    return store.project_dir(project_id) / "agent-settings.json"


def get_settings(project_id):
    store.load_project(project_id)
    data = store.read_json(settings_path(project_id), {})
    effort = data.get("reasoning_effort") if isinstance(data, dict) else None
    return {"reasoning_effort": effort if isinstance(effort, str) and effort in REASONING_EFFORTS else "auto"}


def set_settings(project_id, effort):
    if not isinstance(effort, str) or effort not in REASONING_EFFORTS:
        raise store.StudioError("Невідомий рівень мислення")
    store.load_project(project_id)
    with locked_file(settings_path(project_id).with_suffix(".lock")):
        settings = {"reasoning_effort": effort}
        store.atomic_json(settings_path(project_id), settings)
    return settings


def memory_path(channel_id):
    store.get_channel_folder(channel_id, include_disabled=True)
    return store.DATA_ROOT / "agent-channel-memory" / (channel_id + ".json")


def get_conversation(project_id):
    store.load_project(project_id)
    data = store.read_json(conversation_path(project_id), {})
    return {"messages": data.get("messages", []), "costs": data.get("costs", [])}


def add_message(project_id, role, content):
    if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip() or len(content) > 30000:
        raise store.StudioError("Некоректне повідомлення агента")
    with locked_file(conversation_path(project_id).with_suffix(".lock")):
        data = get_conversation(project_id)
        message = {"id": uuid.uuid4().hex, "role": role, "content": content, "created_at": time.time()}
        data["messages"].append(message)
        store.atomic_json(conversation_path(project_id), data)
    return message


def add_cost(project_id, kind, model, amount, request_id=None):
    if kind not in {"chat", "image"} or not isinstance(model, str) or len(model) > 200:
        raise store.StudioError("Некоректні дані про витрати")
    if amount is not None and (type(amount) not in (int, float) or not math.isfinite(amount) or amount < 0):
        raise store.StudioError("Некоректна сума витрат")
    with locked_file(conversation_path(project_id).with_suffix(".lock")):
        data = get_conversation(project_id)
        entry = {"id": uuid.uuid4().hex, "kind": kind, "model": model, "amount_usd": amount, "request_id": request_id, "created_at": time.time()}
        data["costs"].append(entry)
        store.atomic_json(conversation_path(project_id), data)
    return entry


def cost_summary(costs):
    known = [entry["amount_usd"] for entry in costs if entry.get("amount_usd") is not None]
    return {"known_total_usd": sum(known), "unknown_count": len(costs) - len(known), "request_count": len(costs)}


def get_memory(channel_id):
    data = store.read_json(memory_path(channel_id), {})
    return data.get("text", "") if isinstance(data, dict) else ""


def set_memory(channel_id, text):
    if not isinstance(text, str) or len(text) > 30000:
        raise store.StudioError("Пам'ять каналу занадто велика")
    with locked_file(memory_path(channel_id).with_suffix(".lock")):
        store.atomic_json(memory_path(channel_id), {"text": text, "updated_at": time.time()})
    return text
