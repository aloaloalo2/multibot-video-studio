"""Claude Code's sign-in on this Mac, from the studio's settings (user, 17 November 2026: «в студії в налаштуваннях
можна таке зробити шоб залогінитись? бо дівчині ж теж треба зручний варіант»).

The studio runs Claude Code for the director, the frames, the scripts and thumbnail prompts. When its login expires
every such run stops («Failed to authenticate… claude auth login»). Here the studio reads the state (`auth status`)
and runs `auth login` itself: Claude Code opens the browser, the author signs in there, and a code the page may show is
passed to the waiting command. No password or token passes through the studio.
"""
from __future__ import annotations

import re
import subprocess
import threading
import time

import director
import store
import model_json

LOCK = threading.Lock()
LOGIN: dict = {}            # the one sign-in in progress: proc, url, state, error, started_at
LOGIN_LIMIT = 10 * 60       # a sign-in left unfinished this long is stopped
URL = re.compile(r"https://\S+")
CODE = re.compile(r"[A-Za-z0-9_#.~-]{6,600}")


def status() -> dict:
    """Whether Claude Code is signed in here: {'logged_in', 'email', 'expires_at', 'method'} (or 'error')."""
    try:
        done = subprocess.run([str(director.executable()), "auth", "status"], capture_output=True, text=True, timeout=30)
        data = model_json.loads(done.stdout, kinds=(dict,))
    except RuntimeError as error:
        return {"logged_in": False, "error": str(error)}
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"logged_in": False, "error": "Не вдалося прочитати стан входу Claude Code."}
    return {"logged_in": data.get("loggedIn") is True, "email": data.get("email"),
            "expires_at": data.get("loginExpiresAt"), "method": data.get("authMethod")}


def view() -> dict:
    with LOCK:
        login = {key: LOGIN.get(key) for key in ("state", "url", "error", "started_at")} if LOGIN else None
    return {**status(), "login": login}


def _reader(proc: subprocess.Popen) -> None:
    lines = []
    for line in proc.stdout:
        lines.append(line.strip())
        found = URL.search(line)
        with LOCK:
            if found and LOGIN.get("proc") is proc and not LOGIN.get("url"):
                LOGIN["url"] = found.group(0)
    proc.wait()
    with LOCK:
        if LOGIN.get("proc") is not proc:
            return
        text = " ".join(lines)
        if proc.returncode == 0 and re.search(r"success", text, re.I):
            LOGIN.update(state="done", error=None)
        elif LOGIN.get("state") != "cancelled":
            last = next((line for line in reversed(lines) if line and not URL.search(line)), "")
            LOGIN.update(state="failed", error=(last or "Вхід не завершився. Спробуйте ще раз.")[:300])
        LOGIN.pop("proc", None)


def _limit(proc: subprocess.Popen) -> None:
    time.sleep(LOGIN_LIMIT)
    with LOCK:
        if LOGIN.get("proc") is proc and proc.poll() is None:
            LOGIN.update(state="failed", error="Вхід не завершили за 10 хвилин. Натисніть «Увійти» ще раз.")
            proc.kill()


def start() -> dict:
    """Run `claude auth login`; Claude Code opens the sign-in page itself. Returns the state with the page's address
    once Claude Code has printed it (a few seconds), so the settings can offer it when no browser opened."""
    cancel()
    try:
        command = [str(director.executable()), "auth", "login"]
    except RuntimeError as error:
        raise store.StudioError(str(error), 503) from None
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, start_new_session=True)
    with LOCK:
        LOGIN.clear()
        LOGIN.update(proc=proc, state="waiting", url=None, error=None, started_at=time.time())
    threading.Thread(target=_reader, args=(proc,), daemon=True).start()
    threading.Thread(target=_limit, args=(proc,), daemon=True).start()
    until = time.monotonic() + 10
    while time.monotonic() < until:
        with LOCK:
            if LOGIN.get("url") or LOGIN.get("state") != "waiting":
                break
        time.sleep(.2)
    return view()


def submit_code(code) -> dict:
    """The code the sign-in page shows, passed to the waiting `auth login` (it asks «Paste code here if prompted»)."""
    if not isinstance(code, str) or not CODE.fullmatch(code.strip()):
        raise store.StudioError("Вставте код зі сторінки входу повністю.", 400)
    with LOCK:
        proc = LOGIN.get("proc")
        if not proc or proc.poll() is not None:
            raise store.StudioError("Вхід не чекає коду. Натисніть «Увійти» ще раз.", 409)
        try:
            proc.stdin.write(code.strip() + "\n")
            proc.stdin.flush()
        except OSError:
            raise store.StudioError("Вхід уже завершився. Натисніть «Увійти» ще раз.", 409) from None
    return view()


def cancel() -> dict:
    with LOCK:
        proc = LOGIN.get("proc")
        if proc and proc.poll() is None:
            LOGIN["state"] = "cancelled"
            proc.kill()
    return {"cancelled": True}
