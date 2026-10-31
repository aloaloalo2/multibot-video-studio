#!/usr/bin/env python3
"""One entry point for agents working with VideoKey Studio: short answers, few calls, no clicking.

    python3 tools/studio.py status                          # what runs now (exports, recognition, director, …)
    python3 tools/studio.py projects [words]                # projects whose channel, folder or name hold all the words
    python3 tools/studio.py summary P [--frames 10-20] [--issues] [--json]
    python3 tools/studio.py still P TIME [--frames N] [--cpu]       # TIME: 83.4, 1:23.4, f12 (middle), f12:start, f12:end
    python3 tools/studio.py export P                        # the running export and the latest ones
    python3 tools/studio.py accent P FRAME KIND [options]   # KIND: text, arrow, circle, card, image
    python3 tools/studio.py clear-accents P FRAME
    python3 tools/studio.py replace P (--clip ID | --frame N) FILE
    python3 tools/studio.py transitions P [--share 0.7] [--seed 23] [--replace]
    python3 tools/studio.py ops P FILE.json|-               # several operations from JSON, one undo step
    python3 tools/studio.py sentences P                     # the director: numbered sentences of the voice, the channel's formats
    python3 tools/studio.py frames P FILE.json [--dry-run]  # the director: check and save the frame plan

P is a project id or words that find one project ("Горбунов 23"). Points and sizes are pixels of the project frame as
it looks at the frame's middle moment (as `still P fN` shows it), or with --space photo fractions of the picture.
Every change is checked against the project's revision and applied as one batch; --dry-run shows what would happen.
The studio must run (python3 tools/studio_restart.py starts it). Exports stay the user's button: this tool only reads
their state.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

STUDIO = "http://127.0.0.1:8770"


class Failure(Exception):
    pass


def call(method: str, path: str, body=None, raw: bool = False, timeout: float = 900):
    request = urllib.request.Request(STUDIO + path, method=method, headers={"Content-Type": "application/json", "Accept": "application/json"},
                                     data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read()).get("error")
        except ValueError:
            message = None
        raise Failure(f"{error.code}: {message or error.reason}") from None
    except urllib.error.URLError as error:
        raise Failure(f"Студія не відповідає ({error.reason}). Запуск: python3 tools/studio_restart.py") from None
    return data.decode("utf-8") if raw else json.loads(data)


def fold(text: str) -> str:
    return unicodedata.normalize("NFC", str(text)).casefold().replace("ё", "е")


def clock(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def find_project(ref: str) -> dict:
    """A project by id, or the one project whose channel name, episode folder and title hold all the words of `ref`."""
    channels = {c["id"]: c for c in call("GET", "/api/channels")["channels"]}
    projects = call("GET", "/api/projects")["projects"]
    if re.fullmatch(r"[0-9a-f]{24}", ref):
        found = [p for p in projects if p["id"] == ref]
    else:
        words = fold(ref).split()
        found = [p for p in projects if all(w in fold(" ".join([channels.get(p["channel_id"], {}).get("name", ""), Path(p.get("episode_path") or "").name,
                                                                   p.get("name", "")])) for w in words)]
    if len(found) != 1:
        lines = [f"  {p['id']}  {channels.get(p['channel_id'], {}).get('name', '')} / {Path(p.get('episode_path') or '').name}" for p in found[:20]]
        raise Failure((f"Знайдено {len(found)} проєктів за «{ref}», уточніть:\n" + "\n".join(lines)) if found else f"Проєкт «{ref}» не знайдено")
    return {**found[0], "channel": channels.get(found[0]["channel_id"], {})}


def point(text: str | None):
    if text is None:
        return None
    parts = [float(v) for v in re.split(r"[,x ]+", text.strip()) if v]
    if len(parts) != 2:
        raise Failure(f"Точка «{text}»: потрібно два числа, наприклад 1290,190")
    return parts


def moment(project: dict, text: str) -> float:
    """Seconds from "83.4", "1:23.4" or a frame: "f12" (its middle), "f12:start", "f12:end" (its last video frame)."""
    match = re.fullmatch(r"f(\d+)(?::(start|mid|end))?", text.strip())
    if match:
        data = call("GET", f"/api/projects/{project['id']}/summary?frames={match.group(1)}")
        rows, project["fps"] = data["frames"], data.get("fps")
        if not rows:
            raise Failure(f"Кадр {match.group(1)} не знайдено")
        row, where = rows[0], match.group(2) or "mid"
        fps = float(project.get("fps") or 30)
        return row["start"] + .001 if where == "start" else row["end"] - 1 / fps if where == "end" else (row["start"] + row["end"]) / 2
    minutes, _, seconds = text.rpartition(":")
    return float(minutes or 0) * 60 + float(seconds)


def run_ops(project: dict, ops: list, dry: bool) -> None:
    result = call("POST", f"/api/projects/{project['id']}/ops", {"ops": ops, "expected_revision": project.get("revision"), "dry_run": dry})
    for line in result.get("report", []):
        print(line)
    if dry:
        print(f"(перевірка) дій: {len(result.get('actions', []))}")
        for action in result.get("actions", [])[:40]:
            payload = action["payload"]
            print(f"  {action['type']}: {payload.get('title') or payload.get('clip_id') or payload.get('from_ref', '')} {payload.get('type', '') if action['type'] == 'set_join_transition' else ''}")
    else:
        print(f"застосовано дій: {result.get('applied', 0)}, версія {result.get('revision')}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="що зараз виконується")
    found = commands.add_parser("projects", help="знайти проєкти")
    found.add_argument("words", nargs="*")
    summary = commands.add_parser("summary", help="кадри проєкту коротко, з проблемами")
    summary.add_argument("project")
    summary.add_argument("--frames", help="діапазон номерів, напр. 10-20")
    summary.add_argument("--issues", action="store_true", help="лише кадри з проблемами")
    summary.add_argument("--json", action="store_true")
    still = commands.add_parser("still", help="стоп-кадр експорту в заданий момент")
    still.add_argument("project")
    still.add_argument("time")
    still.add_argument("--frames", type=int, default=1)
    still.add_argument("--cpu", action="store_true", help="рендер FFmpeg навіть там, де є GPU")
    exports = commands.add_parser("export", help="стан експорту")
    exports.add_argument("project")
    accent = commands.add_parser("accent", help="підпис, стрілка, коло, картка чи картинка, прив'язані до руху фото кадру")
    accent.add_argument("project")
    accent.add_argument("frame")
    accent.add_argument("kind", choices=["text", "arrow", "circle", "card", "image"])
    accent.add_argument("--text", help="текст підпису (якщо його каже голос у кадрі, слова з'являються в такт)")
    accent.add_argument("--phrase", help="точні слова голосу в кадрі, з'являються в такт")
    accent.add_argument("--at", help="центр: x,y")
    accent.add_argument("--from", dest="tail", help="початок стрілки: x,y")
    accent.add_argument("--to", dest="head", help="вістря стрілки: x,y")
    accent.add_argument("--bend", type=float, default=.15)
    accent.add_argument("--radii", help="радіуси кола: rx,ry")
    accent.add_argument("--size", help="ширина й висота картки чи картинки: w,h")
    accent.add_argument("--width", type=float, help="найдовший рядок підпису, px")
    accent.add_argument("--font-size", type=int)
    accent.add_argument("--style", choices=["card", "tag", "yellow", "white"])
    accent.add_argument("--entrance", help="поява слів: up, pop, blur_up, fade, …")
    accent.add_argument("--word", help="з'явитися на цьому слові голосу")
    accent.add_argument("--appear", type=float, help="з'явитися через стільки секунд від початку кадру")
    accent.add_argument("--color")
    accent.add_argument("--path", help="файл картинки (kind image)")
    accent.add_argument("--space", choices=["frame", "photo"], default="frame")
    accent.add_argument("--dry-run", action="store_true")
    clear = commands.add_parser("clear-accents", help="прибрати акценти кадру")
    clear.add_argument("project")
    clear.add_argument("frame")
    clear.add_argument("--dry-run", action="store_true")
    replace = commands.add_parser("replace", help="замінити матеріал кліпу, зберігши рух і назву")
    replace.add_argument("project")
    replace.add_argument("file")
    replace.add_argument("--clip")
    replace.add_argument("--frame")
    replace.add_argument("--dry-run", action="store_true")
    transitions = commands.add_parser("transitions", help="переходи на стиках за правилами каналу")
    transitions.add_argument("project")
    transitions.add_argument("--share", type=float, default=.7)
    transitions.add_argument("--seed", type=int, default=23)
    transitions.add_argument("--replace", action="store_true", help="розставити заново, не зберігаючи наявні")
    transitions.add_argument("--dry-run", action="store_true")
    sentences = commands.add_parser("sentences", help="речення озвучки з часом і формати каналу, для режисера")
    sentences.add_argument("project")
    frames = commands.add_parser("frames", help="перевірити й записати план кадрів режисера")
    frames.add_argument("project")
    frames.add_argument("file")
    frames.add_argument("--dry-run", action="store_true")
    ops = commands.add_parser("ops", help="операції з JSON-файлу або stdin")
    ops.add_argument("project")
    ops.add_argument("file")
    ops.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.command == "status":
            data = call("GET", "/api/studio/status")
            print("Студія працює" + (": нічого не виконується" if not data["busy"] else ""))
            for line in data["busy"]:
                print(" · " + line)
            return 0
        if args.command == "projects":
            channels = {c["id"]: c["name"] for c in call("GET", "/api/channels")["channels"]}
            words = fold(" ".join(args.words)).split()
            for p in call("GET", "/api/projects")["projects"]:
                text = " ".join([channels.get(p["channel_id"], ""), Path(p.get("episode_path") or "").name, p.get("name", "")])
                if all(w in fold(text) for w in words):
                    print(f"{p['id']}  {channels.get(p['channel_id'], '')} / {Path(p.get('episode_path') or '').name}  ({p.get('plan_stage') or 'без плану'})")
            return 0
        project = find_project(args.project)
        pid = project["id"]
        if args.command == "summary":
            query = urllib.parse.urlencode({key: value for key, value in (("frames", args.frames), ("issues", "1" if args.issues else None),
                                                                           ("format", None if args.json else "text")) if value})
            text = call("GET", f"/api/projects/{pid}/summary?{query}", raw=True)
            print(text if not args.json else json.dumps(json.loads(text), ensure_ascii=False, indent=1), end="" if not args.json else "\n")
            return 0
        if args.command == "sentences":
            data = call("GET", f"/api/projects/{pid}/director-sentences")
            print(f"Озвучка {clock(data['duration'])}, речень {len(data['sentences'])}. У кадрі до {data['max_sentences']} речень.")
            print(f"Формати каналу, частка тривалості фільму (допуск ±{data['tolerance']:g}):")
            for key, share in data["shares"].items():
                print(f"  {key:<16} {share:>5.1f}%  {data['labels'][key]}: {data['hints'][key]}")
            if data.get("opening"):
                print(f"Перші {data['opening']['count']} кадр(и): {data['opening']['format']}")
            for item in data["sentences"]:
                print(f"{item['number']:>4} [{clock(item['start'])}–{clock(item['end'])}] {item['text']}")
            return 0
        if args.command == "frames":
            body = json.loads(Path(args.file).read_text(encoding="utf-8"))
            frames = body.get("frames") if isinstance(body, dict) else body
            data = call("POST", f"/api/projects/{pid}/director-frames", {"frames": frames, "dry_run": args.dry_run})
            for problem in data.get("problems", []):
                print("! " + problem)
            if data.get("shares"):
                print("Частки: " + ", ".join(f"{key} {data['shares'][key]:.1f}% (канал {data['targets'][key]:.1f}%)" for key in data["targets"]))
            if not data["ok"]:
                return 1
            print(f"Перевірка пройшла: {data['frames']} кадрів" if args.dry_run else f"План кадрів записано в студію: {data['frames']} кадрів")
            return 0
        if args.command == "still":
            at = moment(project, args.time)
            data = call("POST", f"/api/projects/{pid}/still", {"time": at, "frames": args.frames, "cpu": args.cpu})
            for path in data["outputs"]:
                print(path)
            print(f"момент {data['time']:.3f} с, рендер {data['renderer']}{', з кешу' if data.get('cached') else ''}, {data.get('seconds', 0)} с")
            print(f"перегляд: {STUDIO}/channels/{project['channel_id']}/projects/{pid}?t={data['time']:.3f}")
            for note in data.get("notes", []):
                print("! " + note)
            return 0
        if args.command == "export":
            data = call("GET", f"/api/projects/{pid}/exports")
            active = data.get("active")
            if active:
                left = f", лишилось ~{active['remaining_seconds']} с" if active.get("remaining_seconds") else ""
                print(f"іде експорт {active['id']}: {active.get('progress', 0)}%, {active.get('stage')}{left}")
            else:
                print("експорт зараз не йде")
            for job in data.get("jobs", []):
                print(f"  {job['id']} {job['status']:<9} {job.get('progress', 0):>3}%  {job.get('output_path') or job.get('error') or job.get('stage') or ''}")
            return 0
        if args.command == "accent":
            spec = {"op": "accent", "frame": int(args.frame) if args.frame.isdigit() else args.frame, "kind": args.kind, "space": args.space}
            for key, value in (("text", args.text), ("phrase", args.phrase), ("at", point(args.at)), ("from", point(args.tail)), ("to", point(args.head)),
                               ("radii", point(args.radii)), ("size", point(args.size)), ("width", args.width), ("font_size", args.font_size), ("style", args.style),
                               ("entrance", args.entrance), ("word", args.word), ("appear", args.appear), ("color", args.color), ("path", args.path)):
                if value is not None:
                    spec[key] = value
            if args.kind == "arrow":
                spec["bend"] = args.bend
            run_ops(project, [spec], args.dry_run)
            return 0
        if args.command == "clear-accents":
            run_ops(project, [{"op": "clear_accents", "frame": int(args.frame) if args.frame.isdigit() else args.frame}], args.dry_run)
            return 0
        if args.command == "replace":
            if not args.clip and not args.frame:
                raise Failure("Вкажіть --clip або --frame")
            spec = {"op": "replace", "path": str(Path(args.file).expanduser().resolve())}
            spec.update({"clip": args.clip} if args.clip else {"frame": int(args.frame) if args.frame.isdigit() else args.frame})
            run_ops(project, [spec], args.dry_run)
            return 0
        if args.command == "transitions":
            run_ops(project, [{"op": "transitions", "share": args.share, "seed": args.seed, "replace": args.replace}], args.dry_run)
            return 0
        if args.command == "ops":
            text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
            data = json.loads(text)
            run_ops(project, data["ops"] if isinstance(data, dict) else data, args.dry_run)
            return 0
    except Failure as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
