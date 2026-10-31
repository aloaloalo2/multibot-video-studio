"""Run the preview's own JavaScript functions (frontend/*.js) in node, so tests can hold the export to the preview.

The preview draws every frame in the browser and the export draws it in Python and Swift; the two must show the same
picture (user, 31 October 2026). These helpers take named functions out of the frontend files as they are, put them in
one script with the stubs a test gives, and return what the script prints as JSON.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
NODE = shutil.which("node")


def function_source(name: str) -> str:
    """The text of `function name(...){...}` from the frontend, found by matching its braces outside strings."""
    for path in sorted(FRONTEND.glob("*.js")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"(?m)^function " + re.escape(name) + r"\(", text)
        if not match:
            continue
        depth, index, quote = 0, text.index("{", match.end()), None
        start = match.start()
        while index < len(text):
            char = text[index]
            if quote:
                if char == "\\":
                    index += 2
                    continue
                if char == quote:
                    quote = None
            elif char in "'\"":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]
            index += 1
    raise LookupError(f"function {name} not found in the frontend")


def run(functions: list[str], body: str, prelude: str = "") -> object:
    """Evaluate `body` (JavaScript that ends by printing one JSON value) after the named frontend functions."""
    script = prelude + "\n" + "\n".join(function_source(name) for name in functions) + "\n" + body
    result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return json.loads(result.stdout)
