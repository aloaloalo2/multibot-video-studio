"""A compact handoff derived from the accepted plan and existing scene files.

This is a read-only index, never another editable plan. Both an initial build and
a fresh repair session get the same frame ids, timings and scene ownership.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import frame_progress
import store

IMPORT = re.compile(r"(?:from\s*|import\s*\(?\s*)['\"]([^'\"]+)['\"]")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def build(project: dict, request: dict, *, repair: bool = False) -> dict:
    pid = project["id"]
    plan = store.load_project_plan(pid) or {}
    frames = [f for f in plan.get("frames", []) if 1 <= int(f["number"]) <= int(request["frames"])]
    made = set(store.made_frames(project, plan))
    razgon = frame_progress.razgon_project(project)
    story, owners, issues, scene_issues = {}, {}, [], []
    if razgon:
        story = store.read_json(razgon / "story/shots.json", {}) or {}
        linked = store.read_json(razgon / "story/studio_frames.json", {}) or {}
        # A mismatched handoff needs a technical fix before another model call.
        expected = [{k: f.get(k) for k in ("number", "start", "end", "format")} for f in plan.get("frames", [])]
        actual = [{k: f.get(k) for k in ("number", "start", "end", "format")} for f in linked.get("frames", [])]
        if linked.get("script_sha256") != plan.get("script_sha256") or expected != actual:
            issues.append("План студії та story/studio_frames.json розходяться. Потрібно узгодити прив'язку кадрів.")
        for path in sorted((razgon / "scenes").rglob("*.js")):
            source = path.read_text(encoding="utf-8", errors="replace")
            for spec in IMPORT.findall(source):
                if spec.startswith(".") and spec.endswith((".js", ".mjs")) and not (path.parent / spec).is_file():
                    scene_issues.append({"file": str(path.relative_to(razgon)), "missing": spec})
            for shot in frame_progress.taken(source):
                owners.setdefault(shot, []).append(str(path))
    rows = []
    for f in frames:
        shots = [s for s in story.get("shots", []) if s["start"] < f["end"] - .001 and s["end"] > f["start"] + .001]
        takes = []
        for s in shots:
            for part in s.get("parts") or [s]:
                if part["id"] not in takes:
                    takes.append(part["id"])
        rows.append({"number": f["number"], "start": f["start"], "end": f["end"], "format": f.get("format"),
                     "idea_preview": (f.get("visual") or f.get("scene") or "")[:100],
                     "text_preview": " ".join(f.get("sentences", []))[:100],
                     "made": f["number"] in made, "takes": takes,
                     "missing_takes": [t for t in takes if not owners.get(t)],
                     "scene_files": sorted({str(Path(p).relative_to(razgon)) for t in takes for p in owners.get(t, [])})})
    targets = [r["number"] for r in rows if not r["made"]]
    return {"schema": 1, "project_id": pid, "request_id": request["id"],
            "mode": "continue" if request.get("continuation_mode") == "handoff" else "repair" if repair else "build",
            "task_notes": str(request.get("task_notes") or "")[:4000],
            "previous_summary": str(request.get("summary") or "")[-1200:],
            "plan_sha256": digest(plan.get("frames", [])),
            "script_sha256": plan.get("script_sha256"), "razgon_project": str(razgon) if razgon else None,
            "sources": {"plan": str(store.project_plan_file(project) or store.project_dir(pid) / "imported-plan.json"),
                        "shots": str(razgon / "story/shots.json") if razgon else None},
            "issues": issues, "scene_issues": scene_issues, "pending_frames": targets, "frames": rows}


def write(project: dict, request: dict, *, repair: bool = False) -> tuple[Path, str]:
    packet = build(project, request, repair=repair)
    if packet["issues"]:
        raise store.StudioError(" ".join(packet["issues"]), 409)
    path = store.project_dir(project["id"]) / "production-context.json"
    store.atomic_json(path, packet)
    short = path.with_suffix(".txt")
    short.write_text(text(packet), encoding="utf-8")
    pending = ",".join(map(str, packet["pending_frames"])) or "немає"
    summary = f"Єдина карта роботи: {short}\nКадри без готового монтажу: {pending}."
    return path, summary


def text(packet: dict) -> str:
    lines = [f"Проєкт {packet['project_id']}. Карта чинного монтажу, не окремий план.",
             f"Razgon: {packet.get('razgon_project') or 'немає'}", f"План: {packet['sources']['plan']}",
             "Повний зміст конкретних кадрів: tools/studio.py plan <id> --frames N-M."]
    if packet.get("task_notes"):
        lines += ["Збережені побажання автора:", packet["task_notes"]]
    if packet.get("previous_summary"):
        lines += ["Короткий підсумок попередньої роботи:", packet["previous_summary"]]
    for f in packet["frames"]:
        state = "готовий" if f["made"] else "зробити"
        missing = ",".join(f.get("missing_takes", [])) or "немає"
        lines.append(f"{f['number']:03d} {f['start']:.2f}-{f['end']:.2f} {state} {f['format']} "
                     + ",".join(f["takes"]) + " | " + ", ".join(f["scene_files"]) + " | відсутні дублі: " + missing)
    lines.extend("УВАГА: " + issue for issue in packet["issues"])
    lines.extend(f"Відсутній імпорт: {v['file']} -> {v['missing']}" for v in packet.get("scene_issues", []))
    return "\n".join(lines) + "\n"


def instructions(summary: str) -> str:
    return f"""\n\nПередача роботи студією
{summary}
Прочитай цю коротку карту першою. Вона посилається на чинний план, шоти й файли сцен.
Спершу виправ відсутні імпорти з карти: перевірка зображень потребує завантаження всіх модулів.
Збережи їхні номери, таймінги, звук і вже готовий монтаж. Повторно нарізати сценарій та створювати другий набір кадрів не потрібно.
Створюй відсутні кадри; під час правки знайди потрібні сцени за зауваженням автора й редагуй лише їх.
Виправлення починається в новій короткій сесії. Читай конкретні файли з карти та потрібні правила каналу.
Перевірку зображення об'єднай: frame_review.py sheets --frames <змінені кадри> дає три моменти кадру.
Повторно перевір лише змінені сцени та їхні стики з сусідами. Для нового кадру перевірка обов'язкова.
Окремий render.mjs --sheet поверх тих самих перевірених зображень не потрібен.
Помічників, вкладені Claude-сесії та паралельну генерацію не запускай.
Працюй послідовно: один незавершений кадр, його відсутні дублі, збереження коду, перевірка трьох моментів і наступний кадр.
Якщо кадр частково готовий, допиши лише відсутні дублі з карти. Наявні сцени, декорації та бібліотеки використовуй повторно.
Не готуй наперед окремі набори декорацій для всього ролика: допоміжний код додавай лише для поточного кадру.
Після завершення кожного кадру перевір його наявність через tools/studio.py work <id>. Файли сцен є контрольними точками для продовження.
Експорт запускається окремо кнопкою користувача.
"""
