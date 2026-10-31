#!/usr/bin/env python3
"""The steps of one animated episode (What If, Razgon 2D) and where it stands now.

    python3 "VideoKey Studio/tools/episode.py" "What If/04 A Year in Space"

Every step is checked against the real files and the Studio, never against a note: the first unfinished step is the
next thing to do, and the command for it is printed. Nothing is changed by this script.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDIO = "http://127.0.0.1:8770"


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def studio(path: str):
    try:
        with urllib.request.urlopen(STUDIO + path, timeout=5) as response:
            return json.loads(response.read())
    except (OSError, ValueError):
        return None


def project_of(episode: Path):
    plan = read_json(episode / "План видео.json") or {}
    pid = (plan.get("report") or {}).get("project_id")
    if pid:
        return pid
    for channel in (studio("/api/channels") or {}).get("channels", []):
        for item in (studio(f"/api/channels/{channel['id']}/projects") or {}).get("projects", []):
            if Path(item.get("episode_path", "")).resolve() == episode.resolve():
                return item["id"]
    return None


def steps(episode: Path):
    """Yield (title, done, detail, next action) in the order the episode is made."""
    pid = project_of(episode)
    plan = ((studio(f"/api/projects/{pid}/plan") or {}).get("plan") if pid else None) or {}
    project = ((studio(f"/api/projects/{pid}") or {}).get("project") if pid else None) or {}
    link = read_json(episode / "razgon.json") or {}
    razgon = Path(link["project"]) if link.get("project") else None
    synced = plan.get("timing", {}).get("status") == "audio_synced"
    frames = plan.get("frames") or []

    script = episode / "Сценарий.txt"
    yield ("Сценарій погоджено", script.is_file() or synced,
           f"{len(script.read_text(encoding='utf-8').split())} слів" if script.is_file() else "можна без сценарію: його дасть розпізнавання",
           "Написати й погодити сценарій або перейти одразу до озвучки")

    yield ("Озвучка розпізнана, план «За озвучкою»", synced,
           f"{plan['timing']['audio']['duration']:.0f} с, {len(plan['timing']['sentences'])} фраз" if synced else "у студії: «Додайте озвучку ролика»",
           "Перетягнути аудіо у вкладці «План ролика» (або VideoKey Studio/tools/video_plan.py --audio)")

    words = read_json(razgon / "timeline" / "words.json") if razgon else None
    yield ("Проєкт Razgon створено", bool(razgon and razgon.is_dir() and words),
           ("слова сценарію з часом" if (words or {}).get("text") == "script" else "слова з розпізнавання (старий звіт)") if words else "немає",
           f"python3 'VideoKey Studio/tools/razgon_bridge.py' prepare --project-id {pid}")

    shots = (read_json(razgon / "story" / "shots.json") or {}).get("shots", []) if razgon else []
    directed = bool(shots) and all(shot.get("scene") for shot in shots) and (razgon / "story" / "beats.json").is_file()
    yield ("Режисура: епізоди й дублі", directed,
           f"{len(shots)} дублів, {len({s.get('episode') for s in shots})} епізодів" if directed else "story/gen_shots.py ще не написано",
           "Написати story/gen_shots.py і перевірити tools/direction_check.py (у папці Razgon)")

    director_frames = plan.get("frame_source") == "razgon-direction" and not plan.get("director_stale")
    yield ("Кадри студії за режисурою", director_frames,
           f"{len(frames)} кадрів" if director_frames else ("сценарій змінився, режисуру треба оновити" if plan.get("director_stale") else f"зараз {len(frames)} кадрів за реченнями"),
           f'python3 "VideoKey Studio/tools/razgon_bridge.py" plan --razgon "{razgon}"' if razgon else "спершу проєкт Razgon")

    config = read_json(razgon / "config.json") if razgon else {}
    config = config or {}
    yield ("Стиль погоджено", bool(config.get("style_approved")),
           f"стиль {config.get('style', '?')}" + (", погоджено" if config.get("style_approved") else ", не погоджено"),
           "Пробні кадри стилів (/video-styles), після вибору користувача: \"style_approved\": true у config.json")

    # scenes are written either for a «Почати створення відео» request (the first N frames) or for the whole film
    request = project.get("production_request")
    written = {p.name.split("_")[0].upper() for p in (razgon / "scenes" / "shots").glob("*.js")} if razgon else set()
    registered = set()
    if razgon:
        import re
        for p in (razgon / "scenes" / "shots").glob("*.js"):
            text = p.read_text(encoding="utf-8")
            registered |= set(re.findall(r"(?:take|registerShot)\('(e\d+)'", text))
            # a take in several parts registers them in a loop: for (const id of ['e51', 'e52']) take(id, ...)
            for items in re.findall(r"for\s*\(\s*const\s+\w+\s+of\s+\[([^\]]*)\]\s*\)\s*(?:take|registerShot)\(", text):
                registered |= set(re.findall(r"['\"](e\d+)['\"]", items))
    missing_all = [s["id"] for s in shots if s["id"] not in registered]
    if not missing_all and shots:
        yield ("Сцени намальовано", True, f"усі {len(shots)} дублів мають код", "")
    else:
        wanted = {f.get("episode") for f in frames[:request["frames"]] if f.get("episode")} if request else set()
        missing = sorted(wanted - written)
        yield ("Запит «Почати створення відео»", bool(request),
               f"кадри 1–{request['frames']} з {request['total_frames']}" if request else "користувач ще не обрав кількість кадрів",
               "Чекати: користувач натискає «Почати створення відео» у плані або просить увесь ролик")
        if request:
            yield (f"Сцени для кадрів 1–{request['frames']} намальовано", not missing,
                   "усі епізоди мають код" if not missing else "бракує епізодів " + ", ".join(missing),
                   "Написати сцени Razgon цих епізодів, text-check і перегляд «Наживо»")

    # every frame looked at, three stills each, and passed on the current code (tools/frame_review.py in the Razgon kit)
    if razgon and shots and not missing_all:
        r = subprocess.run([sys.executable, "tools/frame_review.py", "--project", str(razgon), "status"], cwd=razgon.parents[1],
                           capture_output=True, text=True)
        lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        yield ("Кадри переглянуто, по 3 стоп-кадри", r.returncode == 0, "; ".join(lines[:3]) or r.stderr.strip()[-200:],
               f'python3 tools/frame_review.py --project "{razgon}" sheets, відкрити кожен build/review/review_NN.png, '
               "mark ok / bug, виправити баги (What If/AGENTS.md, «Перевірка кожного кадру»)")

    # a jump at a junction (camera, pose, face) is a defect: the cut_check report must be newer than the scene code and clean
    if razgon and shots and not missing_all:
        report = razgon / "build" / "cuts" / "report.json"
        code = max((p.stat().st_mtime for d in ("scenes", "story") for p in (razgon / d).rglob("*") if p.suffix in (".js", ".json")), default=0)
        fresh = report.is_file() and report.stat().st_mtime >= code
        bad = [j for j in read_json(report) if str(j.get("status", "")).startswith("FAIL")] if fresh else []
        yield ("Стики без ривків", fresh and not bad,
               ("усі стики чисті" if not bad else f"брак на {len(bad)} стиках: " + ", ".join(f"{j['from']}→{j['to']}" for j in bad[:6])) if fresh
               else "перевірки ще не було або код сцен новіший за неї",
               f'python3 "VideoKey Studio/tools/cut_check.py" --razgon "{razgon}" і виправити кожен FAIL (What If/AGENTS.md, «Стики без ривків»)')

    # a take far slower than the rest puts a filter on each of many draws: the speed check must be newer than the code
    if razgon and shots and not missing_all:
        report = razgon / "build" / "speed_check.json"
        fresh = report.is_file() and report.stat().st_mtime >= code
        slow = (read_json(report) or {}).get("slow", []) if fresh else []
        yield ("Дублі без важких місць", fresh and not slow,
               ("усі дублі рендеряться рівно" if not slow else f"повільні дублі: " + ", ".join(f"{r['id']} {r['ms']} мс" for r in slow[:6])) if fresh
               else "перевірки ще не було або код сцен новіший за неї",
               f'node render.mjs --project "{razgon}" --speed-check у папці What If/razgon-2d-studio і переписати кожен повільний дубль '
               "(What If/AGENTS.md, пункт 5б)")

    finals = sorted(episode.glob("*.mp4"))
    yield ("Фінальний MP4", bool(finals), finals[-1].name if finals else "ще немає",
           f'Після команди користувача: python3 "VideoKey Studio/tools/razgon_bridge.py" push / final --razgon "{razgon}"')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("episode", help="папка випуску, напр. \"What If/04 A Year in Space\"")
    args = parser.parse_args()
    episode = (ROOT / args.episode).resolve() if not Path(args.episode).is_absolute() else Path(args.episode)
    if not episode.is_dir():
        sys.exit(f"Немає папки випуску: {episode}")
    if studio("/api/health") is None:
        print("Увага: студія не відповідає, кроки студії позначено як не виконані")
    print(f"Випуск: {episode.name}")
    next_action = None
    for number, (title, done, detail, action) in enumerate(steps(episode), 1):
        mark = "✓" if done else ("→" if next_action is None else "·")
        if not done and next_action is None:
            next_action = action
        print(f" {mark} {number}. {title} — {detail}")
    print("\nДалі: " + (next_action or "усе готово; публікація тільки з окремого дозволу"))


if __name__ == "__main__":
    main()
