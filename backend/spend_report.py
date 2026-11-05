"""Where a run of Claude Code spent the subscription's limits (user, 4 November 2026: «отчет по витраченим токенам…
можливо, контекст якийсь старий ми читаємо лишній раз»).

Every run of the director and the frame agent leaves its full stream-json log in the project folder. When the run ends,
`record` reads that log and saves a report next to it (`spend/<log>-<time>.json`): the run's cost, the share of each kind
of work (writing scene code, checks with stills, reading files…), the tool results that were re-read on the most turns,
files read more than once, helpers that started with a copy of the whole conversation, a run that resumed an old session,
and short advice. The report never changes the run; it is read through `GET /api/projects/<id>/spend` and
`tools/studio.py spend P`.

Every turn of Claude re-reads the whole conversation from the cache, so the price of a step grows with everything the
agent has seen before it. A turn's cost is put on the action it starts; the context each tool result adds is measured on
the next turn (its cache write) and priced again on every later turn that still carries it.
"""
from __future__ import annotations

import collections
import json
import os
import re
import threading
import time
from pathlib import Path

import store

# $ per million tokens; they match the costs Claude Code reports for these runs (Opus 5.5, 1-hour cache)
PRICE = {"input": 3.0, "output": 15.0, "read": 0.30, "write_1h": 6.0, "write_5m": 3.75}
CHARS_PER_TOKEN = 3.2
FORKED = 150_000      # a helper that starts with more context than this carries a copy of the whole conversation
RESUMED = 150_000     # a run whose first turn already holds this much continued an old session
BILLING_VERSION = 2
SCENE = re.compile(r"/scenes/|\.m?js$")
IMAGE = re.compile(r"\.(png|jpe?g|webp|gif)$", re.I)

GROUPS = ["Код сцен", "Перевірки й стоп-кадри", "Читання файлів та інструкцій", "Режисура", "Асети", "Студія й міст",
          "Роздуми без дій", "Інше"]


def action(name: str, data: dict) -> tuple[str, str]:
    """The group of a tool call and a short line saying what it was."""
    data = data or {}
    path = str(data.get("file_path") or data.get("path") or "")
    short = "/".join(Path(path).parts[-2:]) if path else ""
    if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        if "/story/" in path:
            return "Режисура", f"{name} {short}"
        return ("Код сцен" if SCENE.search(path) else "Інше"), f"{name} {short}"
    if name == "Read":
        if IMAGE.search(path):
            return "Перевірки й стоп-кадри", f"картинка {short}"
        return "Читання файлів та інструкцій", f"читання {short}"
    if name in ("Glob", "Grep"):
        return "Читання файлів та інструкцій", f"{name} {data.get('pattern', '')}"[:90]
    if name == "Skill":
        return "Читання файлів та інструкцій", f"навик {data.get('skill', '')}"
    if name in ("Task", "Agent"):
        return "Інше", f"помічник: {data.get('description') or str(data.get('prompt', ''))[:60]}"
    if name != "Bash":
        return "Інше", name or "?"
    # «cd <folder> && …» says nothing about the work: judge the command after it
    command = re.sub(r"^\s*cd\s+(\"[^\"]*\"|'[^']*'|\S+)\s*&&\s*", "", str(data.get("command") or ""))
    line = re.sub(r"\s+", " ", command).strip()[:90]
    if re.search(r"(open\([^)]*\.m?js['\"]|\bp\s*=\s*['\"][^'\"]+\.m?js['\"]|sed -i\b.*\.m?js)", command):
        return "Код сцен", line
    if re.search(r"frame_review|cut_check|direction_check|text-check|speed-check|--stills|--sheet|contact|render\.mjs|look\w*\.py|PIL|Image\.open|review", command):
        return "Перевірки й стоп-кадри", line
    if re.search(r"codex|split_sheet|library\.py|prompt|propsheet|spec_", command):
        return "Асети", line
    if re.search(r"razgon_bridge|studio\.py|8770|frame_progress", command):
        return "Студія й міст", line
    if re.search(r"gen_shots|shots\.json|bible", command):
        return "Режисура", line
    if re.search(r"^\s*(cat|sed|head|tail|awk|wc|ls|find|grep|rg)\b", command):
        return "Читання файлів та інструкцій", line
    if re.search(r"node -e|python3 -c|python3 - |<<", command):
        return "Перевірки й стоп-кадри", line
    return "Інше", line


def read_target(name: str, data: dict) -> str | None:
    """The file a call reads, to find files read again."""
    if name == "Read":
        return str(data.get("file_path") or "") or None
    if name == "Bash":
        found = re.match(r"\s*(?:cat|sed -n \S+|head(?: -\S+)*|tail(?: -\S+)*)\s+(\"[^\"]+\"|'[^']+'|\S+)\s*$", str(data.get("command") or ""))
        return found.group(1).strip("\"'") if found else None
    return None


def session_file(sid: str) -> Path | None:
    if not re.fullmatch(r"[0-9a-f-]{36}", sid or ""):
        return None
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    cwd = re.sub(r"[^a-zA-Z0-9]", "-", str(store.YOUTUBE_ROOT))
    return config / "projects" / cwd / (sid + ".jsonl")


def session_receipt(sid: str, first_message: str) -> dict:
    """Use the native session total only when the stream covers that session from its first main turn.

    A stopped CLI can omit its result while Claude still saves the total, including helpers and thinking.
    An old resumed session's cumulative total must never be charged again as a new run.
    """
    path = session_file(sid)
    if path is None or not path.is_file() or not first_message:
        return {}
    first, receipt = None, {}
    with path.open(encoding="utf-8", errors="replace") as source:
        for line in source:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "assistant" and not event.get("isSidechain") and first is None:
                first = (event.get("message") or {}).get("id")
                if first != first_message:
                    return {}
            if event.get("type") == "cost-state" and event.get("sessionId") == sid and event.get("modelUsage"):
                receipt = event
    if first != first_message or receipt.get("hasUnknownModelCost"):
        return {}
    return {"modelUsage": receipt.get("modelUsage") or {}, "_native_fresh": True,
            "_receipt_modified": path.stat().st_mtime_ns}


def parse(log: Path) -> tuple[list[dict], dict]:
    """The log's turns in order (one per message, with usage, calls and written characters) and its last result."""
    turns: dict[str, dict] = {}
    calls: dict[str, dict] = {}
    result: dict = {}
    baseline: dict = {}
    sid, first_message = None, None
    with log.open(encoding="utf-8", errors="replace") as source:
        for line in source:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            kind = event.get("type")
            sid = event.get("session_id") or sid
            if kind == "result" and event.get("modelUsage"):
                result = event
                # a resumed session reports what it had already spent before this run made a single step
                if not turns and not baseline:
                    baseline = event
            if kind == "user":
                for part in (event.get("message") or {}).get("content") or []:
                    if isinstance(part, dict) and part.get("type") == "tool_result" and part.get("tool_use_id") in calls:
                        content = part.get("content")
                        items = content if isinstance(content, list) else [{"type": "text", "text": content or ""}]
                        calls[part["tool_use_id"]]["images"] += sum(1 for item in items if item.get("type") == "image")
                continue
            if kind != "assistant":
                continue
            message = event.get("message") or {}
            if first_message is None and not event.get("parent_tool_use_id"):
                first_message = message.get("id")
            key = message.get("id") or f"_{len(turns)}"
            turn = turns.setdefault(key, {"usage": {}, "calls": [], "chars": 0, "agent": event.get("parent_tool_use_id") or "main"})
            turn["usage"] = message.get("usage") or turn["usage"]
            for part in message.get("content") or []:
                if part.get("type") in ("text", "thinking"):
                    turn["chars"] += len(part.get("text") or part.get("thinking") or "")
                elif part.get("type") == "tool_use":
                    data = part.get("input") or {}
                    turn["chars"] += len(json.dumps(data, ensure_ascii=False))
                    group, what = action(part.get("name"), data)
                    call = {"id": part.get("id"), "group": group, "what": what, "images": 0,
                            "reads": read_target(part.get("name"), data)}
                    calls[part.get("id")] = call
                    turn["calls"].append(call)
    if not result.get("modelUsage") and sid:
        result = {**result, **session_receipt(sid, first_message)}
    result["_session_id"] = sid
    native = session_file(sid)
    result["_session_modified"] = native.stat().st_mtime_ns if native and native.is_file() else None
    if result and baseline and baseline is not result:
        # this run only: the session's totals at its end less what the session had spent before it
        usage = {}
        for model, after in (result.get("modelUsage") or {}).items():
            before = (baseline.get("modelUsage") or {}).get(model) or {}
            usage[model] = {key: (value - before.get(key, 0)) if isinstance(value, (int, float)) else value for key, value in after.items()}
        result = {**result, "modelUsage": usage, "resumed_from_usd": sum(float(u.get("costUSD") or 0) for u in (baseline.get("modelUsage") or {}).values())}
    return list(turns.values()), result


def analyse(log: Path) -> dict:
    turns, result = parse(log)
    models = result.get("modelUsage") or {}
    real_cost = sum(float(u.get("costUSD") or 0) for u in models.values()) or None
    first_context = sum(int((turns[0]["usage"] if turns else {}).get(key) or 0)
                        for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    if first_context > RESUMED and "resumed_from_usd" not in result and not result.get("_native_fresh"):
        # a resumed session whose earlier spending is unknown: its totals would count earlier runs too
        models, real_cost = {}, None
    real_out = sum(int(u.get("outputTokens") or 0) for u in models.values())
    thinking = sum(int(u.get("thinkingTokens") or 0) for u in models.values())
    visible_chars = sum(turn["chars"] for turn in turns) or 1
    visible_tokens = max(real_out - thinking, visible_chars / CHARS_PER_TOKEN) if real_out else visible_chars / CHARS_PER_TOKEN
    per_turn_thinking = thinking / len(turns) if turns else 0

    by_agent: dict[str, list[dict]] = collections.defaultdict(list)
    for turn in turns:
        by_agent[turn["agent"]].append(turn)
    totals = collections.Counter()
    for agent, series in by_agent.items():
        for index, turn in enumerate(series):
            usage = turn["usage"]
            cache = usage.get("cache_creation") or {}
            write_1h = int(cache.get("ephemeral_1h_input_tokens") or 0)
            write_5m = int(cache.get("ephemeral_5m_input_tokens") or 0) if cache else int(usage.get("cache_creation_input_tokens") or 0)
            read = int(usage.get("cache_read_input_tokens") or 0)
            fresh = int(usage.get("input_tokens") or 0)
            out = turn["chars"] / visible_chars * visible_tokens + per_turn_thinking
            turn["context"] = read + write_1h + write_5m + fresh
            turn["cost"] = (fresh * PRICE["input"] + write_1h * PRICE["write_1h"] + write_5m * PRICE["write_5m"]
                            + read * PRICE["read"] + out * PRICE["output"]) / 1e6
            turn["added"] = write_1h + write_5m + fresh
            totals.update(input=fresh, cache_write=write_1h + write_5m, cache_read=read)
    estimate = sum(turn["cost"] for turn in turns) or 1
    scale = real_cost / estimate if real_cost else 1.0

    groups = collections.Counter(); group_turns = collections.Counter(); helpers_cost = 0.0
    rebuilds = {"count": 0, "tokens": 0, "usd": 0.0}
    carried: dict[str, dict] = {}
    reads: dict[tuple, dict] = {}
    images = 0
    helpers = []
    for agent, series in by_agent.items():
        if agent != "main":
            first = series[0]["context"]
            cost = sum(turn["cost"] for turn in series) * scale
            helpers_cost += cost
            helpers.append({"turns": len(series), "start_context": first, "max_context": max(t["context"] for t in series),
                            "forked": first > FORKED, "usd": round(cost, 2),
                            "forked_usd": round(sum(min(first, t["context"]) for t in series) * PRICE["read"] / 1e6 * scale, 2) if first > FORKED else 0})
        for index, turn in enumerate(series):
            group = turn["calls"][0]["group"] if turn["calls"] else "Роздуми без дій"
            groups[group] += turn["cost"] * scale; group_turns[group] += 1
            if index == 0:
                continue
            # the cache lives 5 minutes (or an hour): after a longer wait (a Codex sheet, a render) the whole
            # conversation is written to the cache again, which is not the size of the last result
            read = int(turn["usage"].get("cache_read_input_tokens") or 0)
            if read < series[index - 1]["context"] * 0.5 and turn["added"] > 20_000:
                rebuilds["count"] += 1; rebuilds["tokens"] += turn["added"]
                rebuilds["usd"] += turn["added"] * PRICE["write_1h"] / 1e6 * scale
                continue
            if not series[index - 1]["calls"]:
                continue
            previous = series[index - 1]["calls"]
            share = turn["added"] / len(previous)
            # the tokens a result added stay in the context until the conversation is compacted
            life = 0
            for later in series[index + 1:]:
                if later["context"] < turn["context"] * 0.5:
                    break
                life += 1
            for call in previous:
                images += call["images"]
                key = f"{agent}|{call['id']}"
                carried[key] = {"what": call["what"], "group": call["group"], "tokens": int(share), "turns": life,
                                "usd": share * life * PRICE["read"] / 1e6 * scale + share * PRICE["write_1h"] / 1e6 * scale}
                if call["reads"]:
                    entry = reads.setdefault((agent, call["reads"]), {"path": call["reads"], "times": 0, "tokens": 0, "usd": 0.0})
                    entry["times"] += 1
                    if entry["times"] > 1:
                        entry["tokens"] += int(share)
                        entry["usd"] += carried[key]["usd"]

    main = by_agent.get("main") or [{"context": 0}]
    start = main[0]["context"]
    total = real_cost or estimate
    repeated = sorted((r for r in reads.values() if r["times"] > 1), key=lambda r: -r["usd"])
    report = {
        "log": log.name, "kind": "director" if log.name.startswith("director") else "production",
        "made_at": time.time(), "log_modified": log.stat().st_mtime,
        "billing_version": BILLING_VERSION, "session_id": result.get("_session_id"),
        "cost_source": "claude-session" if result.get("_native_fresh") else "stream",
        "receipt_modified": result.get("_receipt_modified"),
        "session_modified": result.get("_session_modified"),
        "model": next(iter(models), None), "cost_usd": round(total, 2), "cost_measured": real_cost is not None,
        "turns": len(turns), "main_turns": len(main) if by_agent.get("main") else 0,
        "tokens": {"input": totals["input"], "cache_write": totals["cache_write"], "cache_read": totals["cache_read"],
                   "output": real_out or int(visible_tokens), "thinking": thinking},
        "start_context": start, "resumed": start > RESUMED,
        "average_context": int(sum(t["context"] for t in turns) / len(turns)) if turns else 0,
        "groups": [{"name": name, "usd": round(groups[name], 2), "share": round(groups[name] / total * 100, 1), "turns": group_turns[name]}
                   for name in sorted(groups, key=lambda n: -groups[n])],
        "helpers": helpers, "helpers_usd": round(helpers_cost, 2), "images": images,
        "most_carried": sorted(({**c, "usd": round(c["usd"], 2)} for c in carried.values()), key=lambda c: -c["usd"])[:10],
        "repeated_reads": [{**r, "usd": round(r["usd"], 2)} for r in repeated[:10]],
        "repeated_usd": round(sum(r["usd"] for r in repeated), 2),
        "cache_rebuilds": {**rebuilds, "usd": round(rebuilds["usd"], 2)},
    }
    report["advice"] = advice(report)
    return report


def advice(report: dict) -> list[str]:
    """What could have been cheaper, in the author's words."""
    notes = []
    total = report["cost_usd"] or 1
    read_usd = report["tokens"]["cache_read"] * PRICE["read"] / 1e6
    if read_usd / total > 0.5:
        notes.append(f"Найбільше коштує перечитування контексту: кожен крок заново читає в середньому "
                     f"{report['average_context'] // 1000} тис. токенів. Коротші сесії й менше картинок у розмові дешевшають кожен наступний крок.")
    if report["resumed"]:
        notes.append(f"Запуск продовжив стару сесію: уже перший крок мав {report['start_context'] // 1000} тис. токенів старої розмови, "
                     f"і кожен крок перечитував їх знову. Для правок дешевше нова сесія з коротким описом того, що вже зроблено.")
    elif report["start_context"] > 40_000:
        notes.append(f"Ще до роботи агент має {report['start_context'] // 1000} тис. токенів інструкцій (AGENTS.md, CLAUDE.md, навики, пам'ять). "
                     f"Їх перечитує кожен крок кожного помічника, тож коротші інструкції дешевшають усю роботу.")
    forked = [h for h in report["helpers"] if h["forked"]]
    if forked:
        notes.append(f"{len(forked)} з {len(report['helpers'])} помічників стартували з копією всієї розмови головного агента "
                     f"(по {min(h['start_context'] for h in forked) // 1000}–{max(h['start_context'] for h in forked) // 1000} тис. токенів); "
                     f"перечитування цієї копії коштувало близько ${sum(h['forked_usd'] for h in forked):.0f}. Помічнику досить короткого завдання.")
    if report["images"] >= 50:
        pictures = sum(c["tokens"] for c in report["most_carried"] if c["what"].startswith("картинка"))
        notes.append(f"Агент переглянув {report['images']} картинок (стоп-кадри, аркуші). Кожна лишається в розмові до кінця сесії й перечитується щокроку"
                     + (f"; найдорожчі з них разом додали {pictures // 1000} тис. токенів." if pictures else "."))
    rebuilds = report.get("cache_rebuilds") or {}
    if rebuilds.get("usd", 0) >= 1:
        notes.append(f"Кеш розмови прострочився {rebuilds['count']} разів (довге очікування Codex, рендеру чи пауза), і щоразу всю розмову "
                     f"записано наново: {rebuilds['tokens'] / 1e6:.1f} млн токенів, близько ${rebuilds['usd']:.0f}. Довгі команди краще "
                     f"запускати у фоні з короткими перевірками або давати помічнику з малим контекстом.")
    if report["repeated_usd"] >= 1:
        notes.append(f"Файли, прочитані повторно в тій самій сесії, коштували близько ${report['repeated_usd']:.0f}.")
    thinking = report["tokens"]["thinking"]
    if thinking and report["tokens"]["output"] and thinking / report["tokens"]["output"] > 0.4:
        notes.append(f"Половину і більше написаного становлять роздуми моделі ({thinking // 1000} тис. токенів): нижче зусилля "
                     f"для простих кадрів заощадило б саме їх.")
    return notes


def text(report: dict) -> str:
    """The report as a few readable lines."""
    lines = [f"{'Режисер' if report['kind'] == 'director' else 'Агент кадрів'} · {report['log']} · "
             f"${report['cost_usd']}{'' if report['cost_measured'] else ' (оцінка)'} · кроків {report['turns']}"
             f" · помічників {len(report['helpers'])}"]
    t = report["tokens"]
    lines.append(f"Токени: перечитано з кешу {t['cache_read'] / 1e6:.1f} млн, записано в кеш {t['cache_write'] / 1e6:.1f} млн, "
                 f"написано {t['output'] / 1e3:.0f} тис. (з них роздуми {t['thinking'] / 1e3:.0f} тис.)")
    lines.append(f"Контекст: на старті {report['start_context'] // 1000} тис., у середньому на крок {report['average_context'] // 1000} тис.")
    rebuilds = report.get("cache_rebuilds") or {}
    if rebuilds.get("count"):
        lines.append(f"Кеш перезаписано наново: {rebuilds['count']} разів, {rebuilds['tokens'] / 1e6:.1f} млн токенів, ${rebuilds['usd']}")
    lines.append("На що пішло:")
    lines += [f"  {g['share']:5.1f}%  ${g['usd']:<8} {g['name']} ({g['turns']} кроків)" for g in report["groups"]]
    if report["most_carried"]:
        lines.append("Найдорожче перечитуваний контекст:")
        lines += [f"  ${c['usd']:<6} {c['tokens'] // 1000} тис. × {c['turns']} кроків  {c['what']}" for c in report["most_carried"][:6]]
    if report["repeated_reads"]:
        lines.append("Прочитано повторно:")
        lines += [f"  ${r['usd']:<6} {r['times']} рази  {r['path']}" for r in report["repeated_reads"][:5]]
    if report["advice"]:
        lines.append("Що можна зекономити:")
        lines += [f"  • {note}" for note in report["advice"]]
    return "\n".join(lines)


def folder(pid: str) -> Path:
    return store.project_dir(pid) / "spend"


def record(log: Path) -> dict | None:
    """Analyse a finished run's log and keep its report beside the project. Never raises: a report is only a report."""
    try:
        if not log.is_file() or log.stat().st_size == 0:
            return None
        report = analyse(log)
        if not report["turns"]:
            return None
        target = folder(log.parent.name)
        target.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(log.stat().st_mtime))
        store.atomic_json(target / f"{log.stem}-{stamp}.json", report)
        import project_costs
        project_costs.record_at(log.parent,'claude_code',report.get('cost_usd'),identity=report.get('log') or str(log),
                                category='production',estimated=not report.get('cost_measured'))
        return report
    except Exception:   # a log that cannot be read must not touch the run it describes
        import traceback
        traceback.print_exc()
        return None


def record_later(log: Path) -> None:
    threading.Thread(target=record, args=(log,), daemon=True).start()


def backfill(pid: str) -> list[dict]:
    """Reports for the logs a project already has (each log once, by its time)."""
    made = []
    for log in sorted(store.project_dir(pid).glob("*.log")):
        if not (log.name.startswith("director") or log.name.startswith("production")):
            continue
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(log.stat().st_mtime))
        saved = folder(pid) / f"{log.stem}-{stamp}.json"
        if saved.is_file():
            previous = store.read_json(saved, {})
            native = session_file(previous.get("session_id"))
            modified = native.stat().st_mtime_ns if native and native.is_file() else None
            if previous.get("billing_version") == BILLING_VERSION and (
                previous.get("session_modified") == modified or
                previous.get("cost_measured") and previous.get("cost_source") == "stream"
            ):
                continue
        report = record(log)
        if report:
            made.append(report)
    return made


def backfill_all() -> None:
    """At start-up no agent runs yet, so every log is complete: report the ones that have no report."""
    root = store.DATA_ROOT / "projects"
    for project in sorted(root.iterdir()) if root.is_dir() else []:
        if project.is_dir() and any(project.glob("*.log")):
            try:
                backfill(project.name)
            except Exception:
                import traceback
                traceback.print_exc()


def reports(pid: str) -> dict:
    """Every saved report of a project, newest first, and the total."""
    store.load_project(pid)
    items = []
    if folder(pid).is_dir():
        for path in folder(pid).glob("*.json"):
            data = store.read_json(path, None)
            if isinstance(data, dict):
                items.append({**data, "file": path.name})
    items.sort(key=lambda r: -float(r.get("log_modified") or 0))
    # a log rewritten by a later run keeps only its newest report
    latest = {}
    for item in items:
        latest.setdefault(item.get("log"), item)
    items = list(latest.values())
    return {"reports": items, "total_usd": round(sum(float(r.get("cost_usd") or 0) for r in items), 2)}
