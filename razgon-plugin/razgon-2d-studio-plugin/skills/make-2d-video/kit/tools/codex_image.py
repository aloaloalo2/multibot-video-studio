"""Draw one picture with Codex (ChatGPT image generation, on the subscription) from a prompt file.

The agent that builds scenes uses it for prop sheets (six transparent props on one sheet, then tools/split_sheet.py):

  python3 tools/codex_image.py --prompt projects/<slug>/assets/src/prompt_A.txt --out projects/<slug>/assets/src/sheet_A.png

The picture and the prompt Codex was given stay next to each other; the exit code is 0 only when the picture exists.
When Codex has run out of its limit, the exit code is 75 and, inside a VideoKey Studio production (VIDEOKEY_PROJECT_ID),
the studio puts the frame job on pause with the reset time: no frames are made without the pictures they need.

Codex takes about a minute a sheet. --background starts the drawing and returns at once, so the agent writes other frames
meanwhile; --wait OUT [OUT …] later waits for those pictures and prints them (or Codex's error, exit 1; the limit, exit 75).
A background drawing stops by itself when the agent that started it is gone (a pause or stop of the studio's job).

  python3 tools/codex_image.py --prompt P.txt --out sheet_A.png --background
  python3 tools/codex_image.py --wait sheet_A.png sheet_B.png
"""
import argparse, datetime, json, os, re, subprocess, sys, time, urllib.request
from pathlib import Path

LIMIT = re.compile(r"usage limit|hit your \w* ?limit|rate limit|quota|too many requests|\b429\b", re.I)


def reset_time(text: str) -> str:
    """When the limit comes back, as Codex said it, in the author's words: «о 17:12», «15 листопада о 09:00»."""
    at = re.search(r"try again at ([^.\n]+)", text, re.I)
    if at:
        raw = at.group(1).strip()
        for fmt in ("%I:%M %p", "%I %p", "%H:%M", "%b %d, %Y %I:%M %p", "%B %d, %Y %I:%M %p", "%b %d %I:%M %p", "%B %d %I:%M %p"):
            try:
                moment = datetime.datetime.strptime(re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", raw).replace(".", ""), fmt)
            except ValueError:
                continue
            return f"о {moment:%H:%M}" if "%b" not in fmt and "%B" not in fmt else f"{moment:%d.%m} о {moment:%H:%M}"
        return raw[:40]
    span = re.search(r"try again in ([^.\n]+)", text, re.I)
    if span:
        units = {"d": 86400, "day": 86400, "h": 3600, "hour": 3600, "m": 60, "min": 60, "minute": 60, "s": 1, "sec": 1, "second": 1}
        total = sum(int(n) * units.get(u.lower().rstrip("s") if len(u) > 1 else u.lower(), 0)
                    for n, u in re.findall(r"(\d+)\s*([a-zA-Z]+)", span.group(1)))
        if total:
            moment = datetime.datetime.now() + datetime.timedelta(seconds=total)
            same_day = moment.date() == datetime.date.today()
            return f"о {moment:%H:%M}" if same_day else f"{moment:%d.%m} о {moment:%H:%M}"
    return ""


def stop_for_limit(text: str) -> None:
    reset = reset_time(text)
    project, studio = os.environ.get("VIDEOKEY_PROJECT_ID"), os.environ.get("VIDEOKEY_STUDIO_URL")
    paused = False
    if project and studio:
        body = json.dumps({"codex_limit": {"reset": reset}}).encode()
        request = urllib.request.Request(f"{studio}/api/projects/{project}/production-pause", body,
                                         {"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(request, timeout=15).read()
            paused = True
        except Exception:
            pass
    sys.stderr.write("CODEX_LIMIT: закінчився ліміт Codex" + (f", він оновиться {reset}" if reset else "") + ". " +
                     ("Студія поставила створення кадрів на паузу. " if paused else "") +
                     "Зупинись: більше нічого не роби й не заміняй картинки стоком чи кодом.\n")
    sys.exit(75)

CODEX = os.environ.get("CODEX_IMAGE_BIN") or "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"

ap = argparse.ArgumentParser()
ap.add_argument("--prompt", help="UTF-8 text file with the picture's description")
ap.add_argument("--out", help="PNG to write")
ap.add_argument("--ref", action="append", default=[], help="reference picture to attach (repeatable)")
ap.add_argument("--background", action="store_true", help="start drawing and return at once; collect it with --wait")
ap.add_argument("--wait", nargs="+", metavar="OUT", help="wait for pictures started with --background")
ap.add_argument("--watch", type=int, help=argparse.SUPPRESS)


def job_file(out: Path) -> Path:
    return out.with_name(out.name + ".job.json")


def agent_pid() -> int:
    """The Claude agent above this command (its Bash shell ends right away); the parent when there is none."""
    pid = os.getppid()
    for _ in range(12):
        try:
            line = subprocess.run(["ps", "-o", "ppid=,command=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        except OSError:
            break
        if not line:
            break
        ppid, command = line.split(None, 1) if " " in line else (line, "")
        if re.search(r"/claude( |$)|claude\.app/Contents/MacOS/claude", command):
            return pid
        if int(ppid) <= 1:
            break
        pid = int(ppid)
    return os.getppid()


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def wait_for(outs) -> None:
    failed, deadline = [], time.monotonic() + 1500
    for raw in outs:
        out = Path(raw).resolve()
        job = job_file(out)
        while time.monotonic() < deadline:
            state = json.loads(job.read_text(encoding="utf-8")) if job.is_file() else {}
            if state.get("status") in ("done", "failed", "limit"):
                break
            if not state and out.is_file():
                state = {"status": "done"}
                break
            if state.get("pid") and not alive(state["pid"]) and not out.is_file():
                state = {"status": "failed", "error": "фоновий запуск Codex зупинився без картинки"}
                break
            time.sleep(2)
        else:
            state = {"status": "failed", "error": "Codex малює довше за 25 хвилин"}
        if state.get("status") == "limit":
            sys.stderr.write(state.get("error", "CODEX_LIMIT") + "\n")
            sys.exit(75)
        if state.get("status") == "done" and out.is_file():
            print(out)
        else:
            failed.append(f"{out.name}: {state.get('error') or 'немає картинки'}")
    if failed:
        sys.exit("Codex не намалював: " + "; ".join(failed))


def draw(a) -> None:
    prompt, out = Path(a.prompt).resolve(), Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    job = job_file(out)
    text = prompt.read_text(encoding="utf-8").strip() + (
        f'\n\nUse the built-in image generation tool and make exactly one image. Save it in the current working directory as '
        f'"{out.name}" and reply only with the saved path.')
    command = [CODEX, "exec", "-s", "workspace-write", "--skip-git-repo-check", "-C", str(out.parent)]
    for ref in a.ref:
        command += ["-i", str(Path(ref).resolve())]

    def finish(status, error=""):
        if a.watch:
            job.write_text(json.dumps({"status": status, "error": error}, ensure_ascii=False), encoding="utf-8")

    try:
        process = subprocess.Popen(command + ["-"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except OSError as error:
        finish("failed", f"Codex не запустився: {error}")
        sys.exit(f"Codex не запустився: {error}. Потрібен застосунок ChatGPT для Mac із входом у підписку")
    started = time.monotonic()
    pending_input = text
    try:
        while True:
            try:
                stdout, stderr = process.communicate(pending_input, timeout=5)
                break
            except subprocess.TimeoutExpired:
                pending_input = None   # communicate keeps the input it was given; a retry must not pass it again
                if a.watch and not alive(a.watch):
                    process.kill()
                    finish("failed", "агент, що запустив малювання, зупинився")
                    sys.exit(1)
                if time.monotonic() - started > 1200:
                    process.kill()
                    finish("failed", "Codex не намалював за 20 хвилин")
                    sys.exit(f"Codex не намалював {out.name} за 20 хвилин: спробуйте ще раз або спростіть промпт")
    finally:
        if process.poll() is None:
            process.kill()
    out.with_suffix(".log.txt").write_text(stdout + stderr, encoding="utf-8")
    if not out.is_file() and LIMIT.search(stdout + stderr):
        reset = reset_time(stdout + stderr)
        finish("limit", "CODEX_LIMIT: закінчився ліміт Codex" + (f", він оновиться {reset}" if reset else "") +
               ". Зупинись: більше нічого не роби й не заміняй картинки стоком чи кодом.")
        stop_for_limit(stdout + stderr)
    if not out.is_file():
        finish("failed", (stderr or stdout)[-300:])
        sys.exit(f"Codex did not save {out.name}: {(stderr or stdout)[-300:]}")
    finish("done")
    print(out)


def main() -> None:
    a = ap.parse_args()
    if a.wait:
        wait_for(a.wait)
        return
    if not a.prompt or not a.out:
        ap.error("--prompt і --out потрібні (або --wait)")
    if a.background:
        out = Path(a.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        args = [sys.executable, os.path.abspath(__file__), "--prompt", str(Path(a.prompt).resolve()), "--out", str(out),
                "--watch", str(agent_pid())] + [x for ref in a.ref for x in ("--ref", str(Path(ref).resolve()))]
        job = job_file(out)
        job.write_text(json.dumps({"status": "drawing"}), encoding="utf-8")
        with open(out.with_name(out.name + ".job.log"), "w") as log:
            child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        job.write_text(json.dumps({"status": "drawing", "pid": child.pid}), encoding="utf-8")
        print(f"Codex малює у фоні: {out}. Пиши інші кадри; потім: python3 {os.path.abspath(__file__)} --wait \"{out}\"")
        return
    draw(a)


if __name__ == "__main__":
    main()
