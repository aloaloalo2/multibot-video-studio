"""Bounded cleanup for workers launched in their own process session."""
import os
import signal
import subprocess


def stop_group(process, children=()):
    if process is None:
        return
    # CLI tools can create separate process sessions. Capture their descendants
    # before terminating the parent, while their ownership is still known.
    for pid in children:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                process.kill()
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # A killed process blocked by the OS must not block the Studio worker too.
            return
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None and not stream.closed:
            try:
                stream.close()
            except OSError:
                pass
