"""Draw one picture with Codex (ChatGPT image generation, on the subscription) from a prompt file.

The agent that builds scenes uses it for prop sheets (six transparent props on one sheet, then tools/split_sheet.py):

  python3 tools/codex_image.py --prompt projects/<slug>/assets/src/prompt_A.txt --out projects/<slug>/assets/src/sheet_A.png

The picture and the prompt Codex was given stay next to each other; the exit code is 0 only when the picture exists.
"""
import argparse, subprocess, sys
from pathlib import Path

CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"

ap = argparse.ArgumentParser()
ap.add_argument("--prompt", required=True, help="UTF-8 text file with the picture's description")
ap.add_argument("--out", required=True, help="PNG to write")
ap.add_argument("--ref", action="append", default=[], help="reference picture to attach (repeatable)")
a = ap.parse_args()
prompt, out = Path(a.prompt).resolve(), Path(a.out).resolve()
out.parent.mkdir(parents=True, exist_ok=True)
text = prompt.read_text(encoding="utf-8").strip() + (
    f'\n\nUse the built-in image generation tool and make exactly one image. Save it in the current working directory as '
    f'"{out.name}" and reply only with the saved path.')
command = [CODEX, "exec", "-s", "workspace-write", "--skip-git-repo-check", "-C", str(out.parent)]
for ref in a.ref:
    command += ["-i", str(Path(ref).resolve())]
result = subprocess.run(command + ["-"], input=text, text=True, capture_output=True, timeout=1200)
out.with_suffix(".log.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
if not out.is_file():
    sys.exit(f"Codex did not save {out.name}: {(result.stderr or result.stdout)[-300:]}")
print(out)
