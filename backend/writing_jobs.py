"""Cancellable author processes, with a receipt even when no terminal answer arrives."""
from contextlib import contextmanager
import json
import os
import signal
import subprocess
import threading
import time

import project_costs
import process_cleanup
import store

LOCK = threading.RLock()
LOCAL = threading.local()
PROCESSES = {}


class Cancelled(Exception):
    pass


@contextmanager
def scope(job):
    previous = getattr(LOCAL, 'job', None)
    LOCAL.job = job
    try:
        yield
    finally:
        LOCAL.job = previous


def check():
    if (getattr(LOCAL, 'job', None) or {}).get('cancelled'):
        raise Cancelled()


def _kill(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def cancel(job):
    with LOCK:
        job['cancelled'] = True
        process = PROCESSES.get(id(job))
        if process is not None:
            _kill(process)


def run(command, prompt, root, identity, timeout=900):
    check()
    job = getattr(LOCAL, 'job', None)
    receipt = root / (identity + '-receipt.json')
    started = time.time()
    record = {'status': 'starting', 'started_at': started, 'identity': identity}
    store.atomic_json(receipt, record)
    # Unknown charges stay unknown if the CLI is interrupted or returns malformed output.
    project_costs.record_at(root, 'claude_code', None, identity=identity, category='script')
    process, answer, output = None, {}, ''
    state = 'failed'
    try:
        with LOCK:
            check()
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, cwd=root, start_new_session=True)
            if job is not None:
                PROCESSES[id(job)] = process
        try:
            output, _ = process.communicate(prompt, timeout=timeout)
            state = 'complete' if process.returncode == 0 else 'failed'
        except subprocess.TimeoutExpired:
            state = 'interrupted'
            _kill(process)
            output, _ = process.communicate(timeout=5)
        for line in reversed(output.strip().splitlines()):
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    answer = value
                    break
            except ValueError:
                continue
        if (job or {}).get('cancelled'):
            state = 'cancelled'
        elif state == 'interrupted':
            raise subprocess.TimeoutExpired(command, timeout)
        check()
        return process.returncode, answer
    finally:
        process_cleanup.stop_group(process)
        if (job or {}).get('cancelled'):
            state = 'cancelled'
        with LOCK:
            if job is not None and PROCESSES.get(id(job)) is process:
                PROCESSES.pop(id(job), None)
        store.atomic_json(receipt, {**answer, **record, 'status': state, 'finished_at': time.time(),
                                    'output': output if not answer else None})
        project_costs.record_at(root, 'claude_code', answer.get('total_cost_usd'), identity=identity, category='script')
