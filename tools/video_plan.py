#!/usr/bin/env python3
"""Submit a script to the planner inside VideoKey Studio."""
from __future__ import annotations
import argparse
import json
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

def studio_request(base_url: str, path: str, payload=None):
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
        raise ValueError("Використовуйте локальну адресу VideoKey Studio")
    request = urllib.request.Request(base_url.rstrip("/") + path,
        data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="GET" if payload is None else "POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            message = json.load(error).get("error", str(error))
        except ValueError:
            message = str(error)
        raise ValueError(message) from None

def main():
    parser = argparse.ArgumentParser(description="Створити карту сценарію у VideoKey Studio")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--channel")
    parser.add_argument("--script", type=Path)
    parser.add_argument("--output", type=Path, help="Додаткова копія готового JSON")
    parser.add_argument("--studio-url", default="http://127.0.0.1:8770")
    parser.add_argument("--pdf", action="store_true", help="Додатковий PDF готової карти")
    parser.add_argument("--duration", type=float)
    parser.add_argument("--audio", type=Path, help="Готова озвучка у папці випуску")
    parser.add_argument("--timings", type=Path, help="JSON з реальними таймінгами кожної фрази")
    parser.add_argument("--hints", type=Path)
    args = parser.parse_args()
    if args.audio and not args.timings:
        parser.error("передайте --audio разом із --timings")
    if not args.list and (not args.channel or not args.script):
        parser.error("потрібні --channel і --script")
    try:
        channels = studio_request(args.studio_url, "/api/channels")["channels"]
        if args.list:
            print("\n".join(item["path"] for item in channels))
            return
        normalized = unicodedata.normalize("NFC", args.channel).casefold()
        matches = [item for item in channels if Path(item["path"]).resolve() == Path(args.channel).expanduser().resolve()
                   or normalized in {unicodedata.normalize("NFC", item[key]).casefold() for key in ("name", "folder_name") if item.get(key)}]
        if len(matches) != 1:
            raise ValueError("Додайте або виберіть канал у VideoKey Studio")
        script = args.script.expanduser().resolve()
        payload = {"channel_id": matches[0]["id"], "name": script.parent.name,
                   "episode_path": str(script.parent), "script_path": str(script)}
        if args.duration is not None:
            payload["duration"] = args.duration
        if args.timings:
            data = json.loads(args.timings.read_text(encoding="utf-8-sig"))
            if args.audio:
                payload["narration"] = {"audio_path": str(args.audio.expanduser().resolve()), "sentences": data if isinstance(data, list) else data["sentences"]}
            else:
                payload["timings"] = data
        if args.hints:
            payload["hints"] = json.loads(args.hints.read_text(encoding="utf-8-sig"))
        result = studio_request(args.studio_url, "/api/projects/generate-plan", payload)
        if result.get("awaiting_voice"):
            # An animated channel: the Studio keeps the script and makes no plan until the voice and the director.
            print(json.dumps({"channel": matches[0]["name"], "awaiting_voice": True, "project_id": result["project"]["id"],
                              "plan_url": args.studio_url.rstrip("/") + result["plan_url"], "script_sha256": result["script_sha256"]},
                             ensure_ascii=False))
            return
        plan = result["plan"]
        report = dict(plan["report"], plan_url=args.studio_url.rstrip("/") + result["plan_url"],
                      generator=plan["generator"], settings_signature=plan["settings_signature"])
        output = args.output.expanduser().resolve().with_suffix(".json") if args.output else Path(report["json"])
        if args.output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.pdf:
            from video_plan_pdf import build_pdf
            frames = plan["frames"]
            report["pdf"] = build_pdf(output.with_suffix(".pdf"), report["channel"],
                [item["sentences"] for item in frames], [(item["start"], item["end"]) for item in frames],
                [item["format"] for item in frames], plan["settings_snapshot"], report["timing_basis"] == "audio_alignment")["pdf"]
        print(json.dumps(report, ensure_ascii=False))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Карту не створено. Перевірте VideoKey Studio: {exc}\n")

if __name__ == "__main__":
    main()
