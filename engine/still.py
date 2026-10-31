#!/usr/bin/env python3
"""A still of the export at one moment, drawn by the export's own renderer.

    python3 engine/still.py --project render-manifest.json --time 83.4 --output still.png [--frames 3] [--cpu]

The engine draws a window of a few frames of the timeline the way «Експорт MP4» draws them (on a Mac with Apple
Silicon through gpu_prepare.py and gpu_render.swift, elsewhere or with --cpu through the FFmpeg renderer) and saves the
first frame as PNG (with --frames N, N PNGs: still-01.png …). The window keeps every clip's keyframes, timed words and
transitions at their real moment, so the still can be held against the preview at the same time. Prints one JSON line
{"output", "outputs", "renderer", "time", "seconds"}.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import render  # noqa: E402


def _gpu(project_file: Path, work: Path, start: float, end: float, video: Path) -> None:
    import gpu_export
    from render_cache import RenderCache, renderer_version
    binary = work / "gpu-render"
    gpu_export._build(ROOT, binary, RenderCache(max_bytes=None), renderer_version(ROOT))
    env = {**os.environ, "STUDIO_GPU_CPU_FALLBACK": "1", "STUDIO_GPU_PROCEDURAL_GRADIENT": "1", "STUDIO_GPU_VIDEO_BLUR": "0",
           "STUDIO_GPU_PERSISTENT_CACHE": "1", "STUDIO_GPU_WINDOW_START": f"{start:.6f}", "GPU_CODEC": "hevc", "GPU_BITRATE": "40000000"}
    for command in ([sys.executable, str(ROOT / "gpu_prepare.py"), str(project_file), str(work), f"{end:.6f}"],
                    [str(binary), str(work / "gpu-project.json"), str(video)]):
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=600)
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr)[-1500:])


def _cpu(project: dict, project_file: Path, work: Path, start: float, end: float, video: Path) -> None:
    width, height, fps = int(project.get("width", 1920)), int(project.get("height", 1080)), int(project.get("fps", 30))
    visual, _, total = render.timeline_plan(project, project_file, width, height, fps)
    parts = []
    for index, (first, last, active) in enumerate(render.timeline_segments(visual, total, fps), 1):
        if last <= start + 1e-9 or first >= end - 1e-9:
            continue
        scene = render.timeline_scene(max(first, start), min(last, end), active, work, width, height, project.get("background", "#101114"))
        folder = work / f"scene-{index:04d}"
        folder.mkdir()
        part = work / f"part-{index:04d}.mp4"
        render.render_scene(scene, project_file, part, folder, width, height, fps, index)
        parts.append(part)
    listing = work / "parts.txt"
    listing.write_text("".join(f"file '{part}'\n" for part in parts), encoding="utf-8")
    subprocess.run([render.FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(video)], check=True)


def still(project_file: Path, moment: float, output: Path, frames: int = 1, cpu: bool = False) -> dict:
    began = time.monotonic()
    project = json.loads(project_file.read_text(encoding="utf-8"))
    width, height, fps = int(project.get("width", 1920)), int(project.get("height", 1080)), int(project.get("fps", 30))
    _, _, total = render.timeline_plan(project, project_file, width, height, fps)
    count = round(total * fps)
    first = max(0, min(count - 1, render.frame_index(moment, fps)))
    frames = max(1, min(frames, count - first, 30))
    start, end = first / fps, (first + frames) / fps
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    gpu = False
    if not cpu:
        import gpu_export
        gpu = gpu_export.available(project, width, height, fps)
    with tempfile.TemporaryDirectory(prefix=".mbvs-still-") as temp:
        work = Path(temp)
        video = work / "window.mp4"
        if gpu:
            _gpu(project_file, work, start, end, video)
        else:
            _cpu(project, project_file, work, start, end, video)
        pattern = output if frames == 1 else output.with_name(output.stem + "-%02d" + output.suffix)
        subprocess.run([render.FFMPEG, "-v", "error", "-y", "-i", str(video), "-frames:v", str(frames), "-start_number", "1", str(pattern)], check=True)
    outputs = [str(output)] if frames == 1 else [str(output.with_name(f"{output.stem}-{k:02d}{output.suffix}")) for k in range(1, frames + 1)]
    return {"output": outputs[0], "outputs": outputs, "renderer": "gpu" if gpu else "cpu", "time": round(start, 6), "frames": frames,
            "seconds": round(time.monotonic() - began, 2)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--time", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=1)
    parser.add_argument("--cpu", action="store_true", help="the FFmpeg renderer even where the GPU one is available")
    args = parser.parse_args()
    try:
        print(json.dumps(still(args.project.expanduser().resolve(), args.time, args.output, args.frames, args.cpu), ensure_ascii=False), flush=True)
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(json.dumps({"error": str(error)[-2000:]}, ensure_ascii=False), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
