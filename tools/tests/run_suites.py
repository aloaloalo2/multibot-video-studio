#!/usr/bin/env python3
"""Run the studio's test suites with several test modules at once.

    python3 tools/tests/run_suites.py                 # backend, engine, tools and frontend
    python3 tools/tests/run_suites.py backend -j 6    # one suite, six modules at a time
    python3 tools/tests/run_suites.py backend engine --slowest 15

Each test module runs in its own Python, so a module's patches and globals never reach another, exactly as in the
one-process command of CLAUDE.md (which still works and stays the reference). The longest modules start first, by the
times of the previous run kept in a file outside the repository; the order changes nothing else. Runs under `nice`, and
by default with half the processors: other work on the Mac stays usable.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUITES = {"backend": (ROOT, "backend/tests"), "engine": (ROOT, "engine/tests"), "tools": (ROOT / "tools", "tests")}
TIMES = Path(tempfile.gettempdir()) / "videokey-test-times.json"


def modules(suite: str) -> list[str]:
    cwd, folder = SUITES[suite]
    return [f"{folder.replace('/', '.')}.{path.stem}" for path in sorted((cwd / folder).glob("test_*.py"))]


def run_module(suite: str, name: str) -> dict:
    cwd, _ = SUITES[suite]
    start = time.monotonic()
    done = subprocess.run(["nice", "-n", "10", sys.executable, "-m", "unittest", name], cwd=cwd,
                          capture_output=True, text=True)
    tail = done.stderr.strip().splitlines()[-1:] or [""]
    ran = re.search(r"Ran (\d+) test", done.stderr)
    return {"suite": suite, "name": name, "ok": done.returncode == 0, "seconds": time.monotonic() - start,
            "tests": int(ran.group(1)) if ran else 0, "summary": tail[0], "output": done.stderr}


def frontend() -> dict:
    start = time.monotonic()
    files = sorted(str(p) for p in (ROOT / "frontend/tests").glob("*.test.cjs"))
    done = subprocess.run(["nice", "-n", "10", "node", "--test", *files], cwd=ROOT, capture_output=True, text=True)
    counts = dict(re.findall(r"^ℹ (tests|pass|fail) (\d+)", done.stdout, re.M))
    return {"suite": "frontend", "name": "frontend/tests", "ok": done.returncode == 0, "seconds": time.monotonic() - start,
            "tests": int(counts.get("tests", 0)), "summary": f"pass {counts.get('pass', '?')}, fail {counts.get('fail', '?')}",
            "output": done.stdout[-6000:]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("suites", nargs="*", help="backend, engine, tools, frontend; типово всі")
    parser.add_argument("-j", "--jobs", type=int, default=max(2, (os.cpu_count() or 4) // 2))
    parser.add_argument("--slowest", type=int, default=10, help="скільки найдовших модулів показати")
    args = parser.parse_args(argv)
    chosen = args.suites or [*SUITES, "frontend"]
    if set(chosen) - {*SUITES, "frontend"}:   # argparse's choices refuse an empty list on Python 3.9
        parser.error("набори: " + ", ".join([*SUITES, "frontend"]))
    try:
        known = json.loads(TIMES.read_text())
    except (OSError, ValueError):
        known = {}
    work = [(suite, name) for suite in chosen if suite in SUITES for name in modules(suite)]
    work.sort(key=lambda item: -known.get(item[1], 5.0))   # the longest first, so none starts last and alone
    start = time.monotonic()
    with ThreadPoolExecutor(args.jobs) as pool:
        futures = [pool.submit(run_module, *item) for item in work]
        if "frontend" in chosen:
            futures.append(pool.submit(frontend))
        results = []
        for future in futures:
            result = future.result()
            results.append(result)
            if not result["ok"]:
                print(f"✗ {result['name']}: {result['summary']}", flush=True)
    wall = time.monotonic() - start
    try:
        TIMES.write_text(json.dumps({**known, **{r["name"]: round(r["seconds"], 2) for r in results}}))
    except OSError:
        pass
    failed = [r for r in results if not r["ok"]]
    for result in failed:
        print(f"\n===== {result['name']} =====\n{result['output'][-6000:]}")
    for suite in chosen:
        rows = [r for r in results if r["suite"] == suite]
        print(f"{suite}: {sum(r['tests'] for r in rows)} тестів, модулів з помилками {sum(not r['ok'] for r in rows)}, "
              f"сумарно {sum(r['seconds'] for r in rows):.0f} с")
    print(f"Найдовші модулі:")
    for r in sorted(results, key=lambda r: -r["seconds"])[:args.slowest]:
        print(f"  {r['seconds']:6.1f} с  {r['name']}")
    print(f"Усього {wall:.0f} с за годинником, {args.jobs} модулів одночасно. " + ("Усе пройшло." if not failed else f"Не пройшли: {len(failed)}."))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
