"""Illustrative cost scenario based on a saved plan and public model rates."""

from __future__ import annotations

import json
import math
import threading
import time
import urllib.request

import agent_openrouter
import agent_storage
import store


IMAGE_MODEL = "black-forest-labs/flux-3-image-klein"
IMAGE_RESOLUTION = "1k"
INPUT_PER_FRAME = 500
OUTPUT_PER_FRAME = 300
_cached = None
_cached_at = 0.0
_lock = threading.Lock()


def get_json(path):
    request = urllib.request.Request(agent_openrouter.BASE + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.load(response)


def rates():
    global _cached, _cached_at
    with _lock:
        if _cached is not None and time.monotonic() - _cached_at < 300:
            return _cached
        try:
            models = get_json("/models")
            model = next(item for item in models["data"] if item.get("id") == agent_openrouter.MODEL)
            pricing = model["pricing"]
            variants = [pricing] + pricing.get("overrides", [])
            token_rates = [(float(item.get("prompt", pricing["prompt"])), float(item.get("completion", pricing["completion"]))) for item in variants]
            if not token_rates or any(not math.isfinite(v) or v < 0 for pair in token_rates for v in pair):
                raise ValueError("Invalid rates")
            endpoints = get_json("/images/models/" + IMAGE_MODEL + "/endpoints")
            image_rates = [float(line["cost_usd"]) for endpoint in endpoints["endpoints"] for line in endpoint.get("pricing", [])
                           if line.get("billable") == "output_image" and line.get("unit") == "image" and str(line.get("variant", "")).lower() == IMAGE_RESOLUTION]
            if not image_rates or any(not math.isfinite(v) or v < 0 for v in image_rates):
                raise ValueError("Image pricing unavailable")
            _cached = {"token_rates": token_rates, "image_rate": min(image_rates)}
            _cached_at = time.monotonic()
            return _cached
        except (OSError, ValueError, KeyError, TypeError, StopIteration):
            raise store.StudioError("Не вдалося отримати поточні тарифи OpenRouter.", 503) from None


def estimate(project_id, prices=None):
    plan = store.load_project_plan(project_id)
    if not isinstance(plan, dict) or not isinstance(plan.get("frames"), list):
        raise store.StudioError("Спочатку створіть план ролика.")
    frames = plan["frames"]
    if not frames:
        raise store.StudioError("У плані немає кадрів.")
    prices = prices or rates()
    image_count = sum(1 for frame in frames if isinstance(frame, dict) and frame.get("format") == "generated_photo")
    video_count = sum(1 for frame in frames if isinstance(frame, dict) and frame.get("format") == "generated_video")
    agent_costs = [len(frames) * (INPUT_PER_FRAME * input_rate + OUTPUT_PER_FRAME * output_rate) for input_rate, output_rate in prices["token_rates"]]
    images = image_count * prices["image_rate"]
    costs = agent_storage.cost_summary(agent_storage.get_conversation(project_id)["costs"])
    return {"frame_count": len(frames), "image_count": image_count, "generated_video_count": video_count,
            "image_model": IMAGE_MODEL, "image_resolution": IMAGE_RESOLUTION, "image_price_usd": prices["image_rate"],
            "images_usd": images, "agent_min_usd": min(agent_costs), "agent_max_usd": max(agent_costs),
            "subtotal_min_usd": images + min(agent_costs), "subtotal_max_usd": images + max(agent_costs),
            "input_tokens_per_frame": INPUT_PER_FRAME, "output_tokens_per_frame": OUTPUT_PER_FRAME,
            "actual": costs}
