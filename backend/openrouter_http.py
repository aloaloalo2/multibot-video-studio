"""One way to send a request to OpenRouter so that a busy provider never stops the studio (user, 18 November 2026:
«нехай підключаються до різних провайдерів… головне, щоб збоїв не було… щоб Open Router завжди відповідав коректно»).

A 429 (the provider or OpenRouter is busy) and a gateway error (502, 503, 504) mean the request was not served and not
billed: it is sent again after a short wait, Retry-After first. A request that never left this Mac (the name did not
resolve, the connection was refused) is sent again too. Any other answer goes back to the caller as before. Chat
requests also let OpenRouter move to another provider of the same model when the first one is busy (`fallbacks`)."""
from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request

RETRY_CODES = {429, 502, 503, 504}
WAITS = (2, 5, 12, 25)   # seconds between tries; about 45 s in all before the answer goes back
MAX_WAIT = 30


def _not_sent(error: urllib.error.URLError) -> bool:
    reason = getattr(error, "reason", error)
    return isinstance(reason, (socket.gaierror, ConnectionRefusedError)) or "nodename nor servname" in str(reason)


def urlopen(request, timeout: float, *, sleep=None):
    """urllib.request.urlopen with the retries above; the response is returned as urlopen returns it."""
    sleep = sleep or time.sleep
    for attempt in range(len(WAITS) + 1):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_CODES or attempt == len(WAITS):
                raise
            retry = (error.headers.get("Retry-After") or "").strip() if error.headers else ""
            sleep(min(int(retry), MAX_WAIT) if retry.isdigit() else WAITS[attempt])
        except urllib.error.URLError as error:
            if not _not_sent(error) or attempt == len(WAITS):
                raise
            sleep(WAITS[attempt])


def fallbacks(payload: dict) -> dict:
    """A chat request may go to another provider of its model when the chosen one is busy."""
    provider = payload.setdefault("provider", {})
    if isinstance(provider, dict):
        provider["allow_fallbacks"] = True
    return payload
