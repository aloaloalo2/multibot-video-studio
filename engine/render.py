#!/usr/bin/env python3
"""Local frame-based renderer for MultiBot Video Studio manifests.

No server, API token, or HyperFrames installation is required. FFmpeg and
FFprobe are the only runtime dependencies. Original media files are read-only.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageFilter, ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from font_catalog import font_path as catalog_font_path
import raster_effects as raster_graphics
import gradient_background
import transition_graphics
import visual_effects


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
FONT_CANDIDATES = (
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


@lru_cache(maxsize=16)
def hardware_hevc_available(width: int, height: int, fps: int) -> bool:
    """Probe the actual output size before choosing the Mac hardware encoder."""
    if sys.platform != "darwin" or not FFMPEG or width * height > 1920 * 1080 or fps > 60:
        return False
    command = [FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error",
               "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={fps}",
               "-frames:v", "1", "-an", "-c:v", "hevc_videotoolbox", "-q:v", "65",
               "-pix_fmt", "yuv420p", "-movflags", "frag_keyframe+empty_moov",
               "-f", "mp4", "pipe:1"]
    try:
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def hardware_export(width: int, height: int, fps: int) -> bool:
    # This switch also provides a deterministic software path for diagnostics.
    return (os.environ.get("MULTIBOT_EXPORT_ENCODER", "auto") != "software"
            and hardware_hevc_available(width, height, fps))


def video_encoder_options(hardware: bool) -> list[str]:
    if hardware:
        return ["-c:v", "hevc_videotoolbox", "-q:v", "65", "-tag:v", "hvc1",
                "-color_range", "tv", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p"]


def emit(stage: str, **fields: Any) -> None:
    print(json.dumps({"stage": stage, **fields}, ensure_ascii=False), flush=True)


def fail(message: str) -> None:
    emit("error", message=message)
    raise SystemExit(1)


def number(value: Any, name: str, minimum: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result


def resolve_source(value: Any, project_file: Path, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} needs a media path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_file.parent / path
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"{field} not found: {path}")
    return path


def source_value(item: dict) -> Any:
    for key in ("source", "src", "file", "path", "asset_path", "media_path"):
        if item.get(key):
            return item[key]
    return None


def normalized_kind(item: dict) -> str:
    kind = str(item.get("type") or item.get("kind") or "").lower()
    if kind in {"photo", "picture"}:
        return "image"
    if kind in {"video", "image", "text", "color"}:
        return kind
    source = source_value(item)
    if source:
        ext = Path(str(source)).suffix.lower()
        if ext in IMAGE_EXT:
            return "image"
        if ext in VIDEO_EXT:
            return "video"
    if item.get("text"):
        return "text"
    raise ValueError(f"Unknown scene type: {kind or source}")


def animation_content_kind(clip: dict) -> str:
    explicit = str(clip.get("content_type") or "").lower()
    if explicit in {"shape", "color", "rectangle"}:
        return "shape"
    if explicit in {"text", "image", "video", "gradient", "graphic_transition"}:
        return explicit
    if explicit:
        raise ValueError(f"Unsupported animation content type: {explicit}")
    if source_value(clip):
        return "video" if Path(str(source_value(clip))).suffix.lower() in VIDEO_EXT else "image"
    if clip.get("text"):
        return "text"
    return "shape"


def first_font(family='Arial',weight=400) -> Path:
    path=catalog_font_path(family,weight)
    if path is None:raise ValueError("No Unicode TrueType font was found")
    return path


@lru_cache(maxsize=4096)
def probe(path: Path) -> dict:
    # Static images need only image validation. Launching FFprobe once for
    # every photo in a long project makes export preparation very slow.
    if path.suffix.lower() in IMAGE_EXT:
        try:
            with Image.open(path) as image:
                width,height=image.size
                image.verify()
            return {'streams':[{'codec_type':'video','width':width,'height':height}],'format':{}}
        except (OSError,ValueError,Image.DecompressionBombError):
            # FFmpeg may support an uncommon image that Pillow cannot read.
            pass
    if not FFPROBE:
        raise RuntimeError("ffprobe is not installed")
    cmd = [FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"Cannot inspect media: {path.name}: {result.stderr.strip()[:300]}")
    return json.loads(result.stdout)


def media_duration(path: Path) -> float:
    data = probe(path)
    try:
        return float(data["format"]["duration"])
    except (KeyError, ValueError, TypeError):
        return 0.0


@lru_cache(maxsize=4096)
def is_static_image(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            return getattr(image, 'n_frames', 1) == 1
    except (OSError, ValueError, Image.DecompressionBombError):
        return False


def offline_sources(project: dict, project_file: Path) -> list[Path]:
    if sys.platform != 'darwin':
        return []
    items=[]
    for layer in project.get('timeline_layers') or []:
        items.extend(layer.get('clips') or [])
    for scene in project.get('scenes') or []:
        items.append(scene)
        items.extend(scene.get('layers') or [])
    for track in project.get('tracks') or []:
        items.append(track)
        items.extend(track.get('clips') or [])
    for kind in ('voice','music'):
        if isinstance(project.get(kind),dict):items.append(project[kind])
    found=set()
    for item in items:
        source=source_value(item)
        if not isinstance(source,str) or not source.strip():
            continue
        path=Path(source).expanduser()
        if not path.is_absolute():path=project_file.parent/path
        try:
            path=path.resolve()
            if os.stat(path).st_flags & 0x40000000:found.add(path)
        except OSError:
            # The normal validation path reports a missing source.
            continue
    return sorted(found)


def cloud_sources_still_offline(paths: list[Path]) -> list[Path]:
    remaining=[]
    for path in paths:
        try:
            if os.stat(path).st_flags & 0x40000000:remaining.append(path)
        except OSError:
            raise RuntimeError(f'Матеріал недоступний: {path.name}') from None
    return remaining


def prepare_cloud_sources(paths: list[Path], *, validate_only: bool = False) -> None:
    if not paths:
        return
    if validate_only:
        raise ValueError(f'Матеріал зберігається в хмарі та ще не завантажений: {paths[0].name}')
    swift=shutil.which('swift')
    helper=Path(__file__).resolve().parent/'icloud_prefetch.swift'
    if not swift or not helper.is_file():
        raise RuntimeError('Завантажте матеріали проєкту з хмари на комп’ютер і повторіть експорт')
    emit('preparing_cloud',completed=0,total=len(paths))
    try:
        result=subprocess.run([swift,str(helper)],input=json.dumps([str(p) for p in paths]),text=True,capture_output=True,timeout=30)
    except subprocess.TimeoutExpired:
        raise RuntimeError('Завантаження матеріалів із хмари не відповідає. Перевірте інтернет і повторіть експорт') from None
    if result.returncode:
        raise RuntimeError('Не вдалося почати завантаження матеріалів із хмари')
    try:
        failures=json.loads(result.stdout).get('failures',[])
    except (ValueError,AttributeError):
        raise RuntimeError('Не вдалося перевірити завантаження матеріалів із хмари') from None
    if failures:
        raise RuntimeError(f'Не вдалося завантажити матеріал із хмари: {failures[0]}')
    deadline=time.monotonic()+900
    remaining=paths
    while remaining:
        remaining=cloud_sources_still_offline(remaining)
        emit('preparing_cloud',completed=len(paths)-len(remaining),total=len(paths))
        if not remaining:
            return
        if time.monotonic()>=deadline:
            raise RuntimeError(f'Матеріали ще завантажуються з хмари: {len(remaining)}. Перевірте інтернет і повторіть експорт')
        time.sleep(1)


def easing_expr(progress: str, mode: str = "linear") -> str:
    p = f"min(1\\,max(0\\,({progress})))"
    if mode == "linear":
        return p
    if mode == "ease_in":
        return f"pow({p}\\,3)"
    if mode == "ease_out":
        return f"(1-pow(1-({p})\\,3))"
    if mode == "ease_in_out":
        return f"(({p})*({p})*(3-2*({p})))"
    raise ValueError("Unsupported motion easing")


def easing_value(progress: float, mode: str = "linear") -> float:
    """Evaluate the bounded easing curve used by easing_expr."""
    p = max(0.0, min(1.0, progress))
    if mode == 'linear': return p
    if mode == 'ease_in': return p ** 3
    if mode == 'ease_out': return 1 - (1 - p) ** 3
    if mode == 'ease_in_out': return p * p * (3 - 2 * p)
    raise ValueError('Unsupported motion easing')


def time_expr(points: list[dict], prop: str, default: float, maximum: int, clock: str = "t", normalize_float: bool = True, easing: str = "linear") -> str:
    pairs = []
    for point in points:
        if prop in point and "time" in point:
            t = number(point["time"], f"keyframe {prop} time")
            value = number(point[prop], f"keyframe {prop}", -maximum * 8)
            if normalize_float and -1 <= value <= 1 and isinstance(point[prop], float):
                value *= maximum
            pairs.append((t, value))
    if not pairs:
        return str(round(default, 4))
    pairs.sort()
    if len({time for time, _ in pairs}) != len(pairs):
        raise ValueError(f"Duplicate {prop} keyframe times")
    expr = str(round(pairs[-1][1], 4))
    for (start, first), (end, second) in reversed(list(zip(pairs[:-1], pairs[1:]))):
        progress = easing_expr(f"(({clock})-{start:.6f})/{end-start:.6f}", easing)
        ramp = f"({first:.6f}+{second-first:.6f}*({progress}))"
        expr = f"if(lt(({clock})\\,{end:.4f})\\,{ramp}\\,{expr})"
    return f"if(lt(({clock})\\,{pairs[0][0]:.4f})\\,{pairs[0][1]:.4f}\\,{expr})"


def scalar_expr(points: list[dict], prop: str, default: float, low: float, high: float, clock: str, easing: str = "linear") -> str:
    """A bounded numeric property with linear interpolation between keyframes."""
    pairs = []
    for point in points:
        if not isinstance(point, dict):
            raise ValueError("keyframes must contain objects")
        if prop in point:
            when = number(point.get("time"), f"{prop} keyframe time")
            value = number(point[prop], f"{prop} keyframe", low)
            if value > high:
                raise ValueError(f"{prop} keyframe exceeds {high}")
            pairs.append((when, value))
    if not pairs:
        return f"{default:.6f}"
    pairs.sort()
    if len({when for when, _ in pairs}) != len(pairs):
        raise ValueError(f"Duplicate {prop} keyframe times")
    expr = f"{pairs[-1][1]:.6f}"
    for (start, first), (end, second) in reversed(list(zip(pairs[:-1], pairs[1:]))):
        progress = easing_expr(f"(({clock})-{start:.6f})/{end-start:.6f}", easing)
        ramp = f"({first:.6f}+{second-first:.6f}*({progress}))"
        expr = f"if(lt(({clock})\\,{end:.6f})\\,{ramp}\\,{expr})"
    return f"if(lt(({clock})\\,{pairs[0][0]:.6f})\\,{pairs[0][1]:.6f}\\,{expr})"


def scalar_value(points: list[dict], prop: str, default: float, clock: float, easing: str) -> float:
    """Evaluate the same keyframe curve used by scalar_expr for one frame."""
    pairs = sorted((float(p['time']), float(p[prop])) for p in points if prop in p)
    if not pairs:
        return default
    if clock <= pairs[0][0]:
        return pairs[0][1]
    for (start, first), (end, second) in zip(pairs, pairs[1:]):
        if clock < end:
            p = max(0.0, min(1.0, (clock-start)/(end-start)))
            if easing == 'ease_in': p = p**3
            elif easing == 'ease_out': p = 1-(1-p)**3
            elif easing == 'ease_in_out': p = p*p*(3-2*p)
            return first+(second-first)*p
    return pairs[-1][1]


def sampled_motion_speeds(layer: dict, duration: float, fps: int, width: int, height: int) -> list[float]:
    """Sample the same motion-speed expression used by the trail gate."""
    offset=float(layer.get('keyframe_offset',0))
    easing=layer.get('easing','linear')
    normalized=layer.get('position_units')!='pixels'
    points=[]
    for point in layer.get('keyframes') or []:
        adjusted=dict(point)
        for key,maximum in (('x',width),('y',height)):
            value=adjusted.get(key)
            if normalized and isinstance(value,float) and -1<=value<=1:
                adjusted[key]=value*maximum
        points.append(adjusted)
    defaults={key:(pixel(layer.get(key),maximum,0) if normalized else float(layer.get(key,0)))
              for key,maximum in (('x',width),('y',height))}
    speeds=[]
    for frame in range(math.ceil(duration*fps)):
        now=frame/fps+offset;past=max(0,now-.02)
        dx=scalar_value(points,'x',defaults['x'],now,easing)-scalar_value(points,'x',defaults['x'],past,easing)
        dy=scalar_value(points,'y',defaults['y'],now,easing)-scalar_value(points,'y',defaults['y'],past,easing)
        speeds.append(math.hypot(dx,dy)/.02)
    return speeds


def visible_motion_trail_end(layer: dict, duration: float, fps: int, width: int, height: int) -> float:
    """Find the last frame where the 180px/s trail gate may be visible."""
    speeds=sampled_motion_speeds(layer,duration,fps,width,height)
    # Keep a small margin around the gate for FFmpeg expression rounding.
    last_visible=max((i for i,speed in enumerate(speeds) if speed>=179),default=-1)
    return min(duration,(last_visible+1)/fps) if last_visible>=0 else 0


def pixel(value: Any, maximum: int, default: float = 0) -> float:
    if value is None:
        return default
    result = number(value, "position", -maximum)
    if isinstance(value, float) and -1 <= result <= 1:
        return result * maximum
    return result


def dimension(value: Any, maximum: int, default: int) -> int:
    if value is None:
        return default
    result = number(value, "size", 0)
    if isinstance(value, float) and 0 < result <= 1:
        result *= maximum
    result = int(round(result))
    if result < 1:
        raise ValueError("layer size must be positive")
    return result


def font_size(layer: dict, height: int) -> int:
    raw = layer.get("font_size", layer.get("size", 54))
    return int(min(max(number(raw, "font size", 8), 8), max(24, height // 3)))


def text_bitmap(layer: dict, path: Path, frame_width: int, frame_height: int) -> tuple[int, int]:
    content = str(layer.get("text", ""))
    if not content:
        raise ValueError("Text layer has no content")
    requested_size = font_size(layer, frame_height)
    max_width = dimension(layer.get("width"), frame_width, int(frame_width * .82))
    max_width = min(max_width, frame_width)
    max_height = dimension(layer.get("height"), frame_height, frame_height)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for size in range(requested_size, 11, -2):
        font = ImageFont.truetype(str(first_font(layer.get('font_family','Arial'),layer.get('font_weight',400))), size)
        if layer.get('font_weight'):
            try:font.set_variation_by_axes([min(a['maximum'],max(a['minimum'],float(layer['font_weight']))) if b'Weight' in a['name'] else a['default'] for a in font.get_variation_axes()])
            except (OSError,AttributeError):pass
        lines = []
        for paragraph in content.splitlines() or [content]:
            current = ""
            for word in paragraph.split():
                candidate = word if not current else current + " " + word
                if current and measure.textlength(candidate, font=font) > max_width:
                    lines.append(current)
                    current = word
                else:
                    current = candidate
            lines.append(current)
        if not lines:
            lines = [content]
        line_height = int(size * float(layer.get('line_height',1.28)))
        line_width = max(measure.textlength(line, font=font) for line in lines)
        required_height = max(1, line_height * len(lines))
        if required_height + 4 <= min(frame_height, max_height) and line_width <= max_width - 4:
            break
    else:
        raise ValueError("Text does not fit inside its frame box")
    # Layout in a logical line box, as the browser does. Pillow's default
    # top anchor includes the font's ascender offset: drawing at y=2 into a
    # line-height-sized image cropped Literata's descenders. Ink may also
    # extend beyond a glyph's advance width or above the font's ascent.
    # Symmetric padding preserves the logical centre of words and letters.
    logical_width = max_width if layer.get('text_align') in {'left','right'} else max(1, math.ceil(line_width))
    ascent, descent = font.getmetrics()
    baseline = (line_height - ascent - descent) / 2 + ascent
    positions = []
    ink_bounds = []
    for line_number, line in enumerate(lines):
        advance = measure.textlength(line, font=font)
        align = layer.get('text_align', 'center')
        x = logical_width - advance if align == 'right' else 0 if align == 'left' else (logical_width - advance) / 2
        y = baseline + line_number * line_height
        positions.append((x, y))
        ink_bounds.append(measure.textbbox((x, y), line, font=font, anchor='ls'))
    pad_x = max(2, math.ceil(-min(b[0] for b in ink_bounds)) + 2,
                math.ceil(max(b[2] for b in ink_bounds) - logical_width) + 2)
    pad_y = max(2, math.ceil(-min(b[1] for b in ink_bounds)) + 2,
                math.ceil(max(b[3] for b in ink_bounds) - required_height) + 2)
    bitmap_width = logical_width + 2 * pad_x
    bitmap_height = required_height + 2 * pad_y
    bitmap = Image.new("RGBA", (bitmap_width, bitmap_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bitmap)
    try:
        rgb = ImageColor.getrgb(str(layer.get("color", "white")))
    except ValueError as exc:
        raise ValueError("Text layer has invalid color") from exc
    for line, (x, y) in zip(lines, positions):
        draw.text((x + pad_x, y + pad_y), line, font=font, fill=(*rgb, 255), anchor='ls')
    if layer.get('raster_blur'):
        radius=float(layer['raster_blur']);pad=math.ceil(radius*3)
        bitmap=ImageOps.expand(bitmap,border=pad,fill=(0,0,0,0)).filter(ImageFilter.GaussianBlur(radius))
        bitmap_width,bitmap_height=bitmap.size
    bitmap.save(path)
    return bitmap_width, bitmap_height


def video_input(cmd: list[str], path: Path, kind: str, trim_start: float = 0, cache_still: bool = False) -> None:
    if kind == "image":
        cmd += ([] if cache_still else ["-loop", "1"]) + ["-framerate", "30", "-i", str(path)]
    else:
        if trim_start:
            cmd += ["-ss", f"{trim_start:.6f}"]
        cmd += ["-i", str(path)]


def render_parallelism(width: int, height: int, fps: int) -> tuple[int, int]:
    """Bound concurrent FFmpeg work while keeping 1080p exports busy."""
    if width * height <= 1920 * 1080 and fps <= 30 and (os.cpu_count() or 1) >= 8:
        return 3, 2
    return 2, 4


def render_scene(scene: dict, project_file: Path, output: Path, work: Path, width: int, height: int, fps: int, index: int) -> None:
    kind = normalized_kind(scene)
    duration = number(scene.get("duration", scene.get("length")), f"scene {index} duration")
    minimum_duration = 1 / fps
    if duration < minimum_duration:
        # Subtracting frame-aligned absolute times can produce 0.03999999999996
        # for a valid 25 fps frame. Preserve real short-duration errors.
        if minimum_duration - duration > 1e-8:
            raise ValueError(f"scene {index} duration must be at least {minimum_duration}")
        duration = minimum_duration
    trim_start = number(scene.get("trim_start", scene.get("source_start", scene.get("offset", 0))), f"scene {index} trim_start")
    cache_stills = os.environ.get('MULTIBOT_STILL_CACHE','1')!='0'
    base_cached = False
    _, filter_threads = render_parallelism(width, height, fps)
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-filter_complex_threads", str(filter_threads), "-y"]
    if kind in {"image", "video"}:
        source = resolve_source(source_value(scene), project_file, f"scene {index}")
        info = probe(source)
        if not any(stream.get("codec_type") == "video" for stream in info.get("streams", [])):
            raise ValueError(f"scene {index} source has no video or image stream")
        available = media_duration(source)
        if kind == "video" and available and trim_start >= available:
            raise ValueError(f"scene {index} trim_start is beyond source duration")
        if kind == "video" and available and trim_start + duration > available + 1 / fps:
            raise ValueError(f"scene {index} video source ends before the planned scene; trim it or choose a longer clip")
        base_cached = cache_stills and kind=='image' and is_static_image(source)
        video_input(cmd, source, kind, trim_start, base_cached)
    else:
        color = str(scene.get("color", "#101114"))
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError(f"scene {index} has invalid color")
        cmd += ["-f", "lavfi", "-i", f"color=c=0x{color[1:]}:s={width}x{height}:r={fps}:d={duration:.6f}"]
    layers = scene.get("layers") or []
    if not isinstance(layers, list):
        raise ValueError(f"scene {index} layers must be an array")
    render_layers = []
    if kind == "text" and scene.get("text"):
        render_layers.append({"type": "text", "text": str(scene["text"]), "color": scene.get("text_color", "white"), "font_size": scene.get("font_size", max(24, height // 14)), "center": True})
    for original in layers:
        if original.get('motion_blur') and normalized_kind(original)=='image':
            trail_end=visible_motion_trail_end(original,duration,fps,width,height)
            if trail_end:
                for fraction,weight in [(1,.1),(.5,.18)]:
                    render_layers.append({**original,'duration':min(float(original.get('duration',duration)),trail_end),'motion_lag':.5/fps*fraction,'trail_strength':weight*float(original['motion_blur'])})
        render_layers.append(original)
    prepared = []
    for layer_index, layer in enumerate(render_layers):
        if not isinstance(layer, dict):
            raise ValueError(f"scene {index} layer {layer_index} must be an object")
        layer_kind = normalized_kind(layer)
        if layer_kind == "text":
            path = work / f"scene-{index:04d}-text-{layer_index:02d}.png"
            bitmap_width, bitmap_height = text_bitmap(layer, path, width, height)
            if layer.get("center"):
                layer = {**layer, "x": (width - bitmap_width) / 2, "y": (height - bitmap_height) / 2}
            elif layer.get("position_units") == "normalized" or (
                isinstance(layer.get("x"), float) and isinstance(layer.get("y"), float)
                and 0 <= layer["x"] <= 1 and 0 <= layer["y"] <= 1
            ):
                adjusted_points = []
                for point in layer.get("keyframes") or []:
                    updated = dict(point)
                    if "x" in updated and (layer.get("position_units") == "normalized" or
                                           (isinstance(updated["x"], float) and -1 <= updated["x"] <= 1)):
                        updated["x"] = updated["x"] * width - bitmap_width / 2
                    if "y" in updated and (layer.get("position_units") == "normalized" or
                                           (isinstance(updated["y"], float) and -1 <= updated["y"] <= 1)):
                        updated["y"] = updated["y"] * height - bitmap_height / 2
                    adjusted_points.append(updated)
                layer = {**layer, "x": layer["x"] * width - bitmap_width / 2,
                         "y": layer["y"] * height - bitmap_height / 2, "keyframes": adjusted_points,
                         "position_units": "pixels"}
            layer_width, layer_height = bitmap_width, bitmap_height
            input_kind = "image"
        if layer_kind in {"image", "video"}:
            path = resolve_source(source_value(layer), project_file, f"scene {index} layer {layer_index}")
            layer_width = dimension(layer.get("width"), width, width // 3)
            layer_height = dimension(layer.get("height"), height, height // 3)
            input_kind = layer_kind
        if layer_kind not in {"image", "video", "text"}:
            raise ValueError(f"Unsupported layer type: {layer_kind}")
        if input_kind=='image' and (layer.get('mask','none')!='none' or layer.get('shadow') or layer.get('blur')):
            path,layer_width,layer_height,pad=raster_graphics.decorate(path,layer_width,layer_height,layer,work)
            if layer.get('position_units')=='pixels':x,y=float(layer.get('x',0)),float(layer.get('y',0));points=[dict(p) for p in layer.get('keyframes',[])]
            else:
                x,y=pixel(layer.get('x'),width,0),pixel(layer.get('y'),height,0)
                points=[{**p,**({'x':pixel(p['x'],width,0)} if 'x' in p else {}),**({'y':pixel(p['y'],height,0)} if 'y' in p else {})} for p in layer.get('keyframes',[])]
            layer={**layer,'x':x-pad,'y':y-pad,'position_units':'pixels','keyframes':[{**p,**({'x':p['x']-pad} if 'x' in p else {}),**({'y':p['y']-pad} if 'y' in p else {})} for p in points]}
        still_cached=cache_stills and input_kind=='image' and is_static_image(path)
        video_input(cmd, path, input_kind, number(layer.get("trim_start", 0), "layer trim_start"), still_cached)
        prepared.append((len(prepared) + 1, layer, layer_width, layer_height, input_kind, still_cached))
    filters = []
    current = "v0"
    base_still_pad = f'tpad=stop_mode=clone:stop_duration={duration+1:.6f},' if base_cached else ''
    base = f"[0:v]{base_still_pad}fps={fps},scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,tpad=stop_mode=clone:stop_duration={duration:.6f},trim=duration={duration:.6f},setpts=PTS-STARTPTS,format=yuv420p[{current}]"
    filters.append(base)
    for layer_index, (input_index, layer, layer_width, layer_height, input_kind, still_cached) in enumerate(prepared):
        start = number(layer.get("start", 0), "layer start")
        end = min(duration, start + number(layer.get("duration", duration - start), "layer duration"))
        if end <= start:
            continue
        if layer.get("position_units") == "pixels":
            x = number(layer.get("x", 0), "layer x", -width * 8)
            y = number(layer.get("y", 0), "layer y", -height * 8)
        else:
            x = pixel(layer.get("x"), width, 0)
            y = pixel(layer.get("y"), height, 0)
        keyframes = layer.get("keyframes") or []
        if not isinstance(keyframes, list):
            raise ValueError("keyframes must be an array")
        elapsed = number(layer.get("keyframe_offset", 0), "keyframe offset")
        clip_length = number(layer.get("clip_duration", duration), "clip duration", 0.01)
        easing = layer.get("easing", "linear")
        lag=float(layer.get('motion_lag',0));motion_clock=f'max(0\\,t+{elapsed:.6f}-{lag:.6f})' if lag else f't+{elapsed:.6f}'
        x_expr = time_expr(keyframes, "x", x, width, motion_clock, layer.get("position_units") != "pixels", easing)
        y_expr = time_expr(keyframes, "y", y, height, motion_clock, layer.get("position_units") != "pixels", easing)
        opacity = number(layer.get("opacity", 1), "layer opacity")
        if opacity > 1:
            raise ValueError("layer opacity must not exceed 1")
        scale = number(layer.get("scale", 1), "layer scale", 0.05)
        if scale > 8:
            raise ValueError("layer scale must not exceed 8")
        scale_expr = scalar_expr(keyframes, "scale", scale, 0.05, 8, motion_clock, easing)
        if layer.get('scale_anchor')=='center':
            x_expr=f'({x_expr})+{layer_width}*(1-({scale_expr}))/2'
            y_expr=f'({y_expr})+{layer_height}*(1-({scale_expr}))/2'
        alpha_expr = scalar_expr(keyframes, "opacity", opacity, 0, 1, f"T+{elapsed:.6f}", easing)
        if lag:
            normalize=layer.get('position_units')!='pixels';differences=[]
            for prop,base,maximum in [('x',x,width),('y',y,height)]:
                now=time_expr(keyframes,prop,base,maximum,f'T+{elapsed:.6f}',normalize,easing)
                past=time_expr(keyframes,prop,base,maximum,f'max(0\\,T+{elapsed:.6f}-.02)',normalize,easing)
                differences.append(f'pow(({now})-({past})\\,2)')
            alpha_expr=f'({alpha_expr})*{layer["trail_strength"]:.6f}*gte(sqrt({"+".join(differences)})/.02\\,180)'
        for direction in ('in','out'):
            join=layer.get('join_'+direction)
            if not join:continue
            offset=float(layer.get('global_offset',0));seam=float(join['seam']);length=float(join['duration']);mode=join['type'];incoming=direction=='in'
            if mode in transition_graphics.PRESETS:
                if transition_graphics.PRESETS[mode].get('kind') == 'cinematic':
                    ap=easing_expr(f'(T+{offset:.6f}-{seam:.6f})/{length:.6f}','ease_in_out')
                    alpha_expr=f'({alpha_expr})*({ap if incoming else "1-("+ap+")"})'
                    continue
                switch=seam+length*.5;gate=f'gte(T+{offset:.6f}\\,{switch:.6f})' if incoming else f'lt(T+{offset:.6f}\\,{switch:.6f})'
                alpha_expr=f'({alpha_expr})*({gate})'
                continue
            p=easing_expr(f'(t+{offset:.6f}-{seam:.6f})/{length:.6f}','ease_in_out')
            ap=easing_expr(f'(T+{offset:.6f}-{seam:.6f})/{length:.6f}','ease_in_out')
            if mode=='crossfade':alpha_expr=f'({alpha_expr})*({ap if incoming else "1-("+ap+")"})'
            if mode.startswith('slide_'):
                q=f'(1-({p}))' if incoming else p
                sign=1 if mode in ('slide_left','slide_up') and incoming or mode in ('slide_right','slide_down') and not incoming else -1
                if mode in ('slide_left','slide_right'):x_expr=f'({x_expr})+{sign*width}*({q})'
                else:y_expr=f'({y_expr})+{sign*height}*({q})'
            if mode.startswith('zoom_'):
                group_scale=f'(.88+.12*({p}))' if incoming and mode=='zoom_in' else f'(1+.12*({p}))' if not incoming and mode=='zoom_in' else f'(1.12-.12*({p}))' if incoming else f'(1-.12*({p}))'
                x_expr=f'{width}/2+(({x_expr})-{width}/2)*({group_scale})';y_expr=f'{height}/2+(({y_expr})-{height}/2)*({group_scale})';scale_expr=f'({scale_expr})*({group_scale})'
                alpha_expr=f'({alpha_expr})*({ap if incoming else "1-("+ap+")"})'
        fade_in = number(layer.get("fade_in", 0), "fade in")
        fade_out = number(layer.get("fade_out", 0), "fade out")
        slide_in = number(layer.get("slide_in", 0), "slide in")
        slide_out = number(layer.get("slide_out", 0), "slide out")
        if fade_in:
            alpha_expr = f"({alpha_expr})*({easing_expr(f'(T+{elapsed:.6f})/{fade_in:.6f}', easing)})"
        if fade_out:
            alpha_expr = f"({alpha_expr})*({easing_expr(f'({clip_length:.6f}-T-{elapsed:.6f})/{fade_out:.6f}', easing)})"
        if slide_in:
            x_expr = f"({x_expr})+{width}*(1-({easing_expr(f'(t+{elapsed:.6f})/{slide_in:.6f}', easing)}))"
        if slide_out:
            x_expr = f"({x_expr})-{width}*(1-({easing_expr(f'({clip_length:.6f}-t-{elapsed:.6f})/{slide_out:.6f}', easing)}))"
        overlay_label = f"ov{layer_index}"
        first_scale = f"scale={layer_width}:{layer_height}" if layer.get("stretch") else f"scale={layer_width}:{layer_height}:force_original_aspect_ratio=decrease"
        still_pad=f'tpad=stop_mode=clone:stop_duration={end+1:.6f},' if still_cached else ''
        overlay_filters = [f"[{input_index}:v]{still_pad}fps={fps}", first_scale, "format=rgba"]
        overlay_filters.extend(visual_effects.filters(layer.get('visual_effect')))
        if input_kind=='video' and layer.get('blur'):
            overlay_filters.append(f"gblur=sigma={float(layer['blur']):.3f}")
        animated_opacity = any('opacity' in point for point in keyframes)
        speeds=sampled_motion_speeds(layer,end,fps,width,height) if lag else []
        safe_motion_gate=not lag or all(abs(speed-180)>1 for speed in speeds)
        transition_alpha=bool(fade_in or fade_out or layer.get('join_in') or layer.get('join_out'))
        fast_alpha = (input_kind=='image' and (animated_opacity or lag or transition_alpha) and safe_motion_gate
                      and os.environ.get('MULTIBOT_FAST_ALPHA','1')!='0'
                      and (not transition_alpha or os.environ.get('MULTIBOT_FAST_TRANSITION_ALPHA','1')!='0'))
        if fast_alpha:
            # Alpha is uniform for a given frame. Change the mixer once per
            # frame instead of repeating the same keyframe math per pixel.
            target=f'colorchannelmixer@alpha_{layer_index}'
            def frame_alpha(frame):
                t=frame/fps
                value=scalar_value(keyframes,'opacity',opacity,t+elapsed,easing)
                if lag:value*=float(layer['trail_strength']) if speeds[frame]>=180 else 0
                for side in ('in','out'):
                    join=layer.get('join_'+side)
                    if not join:continue
                    mode=join['type'];incoming=side=='in'
                    position=t+float(layer.get('global_offset',0));seam=float(join['seam']);length=float(join['duration'])
                    if mode in transition_graphics.PRESETS and transition_graphics.PRESETS[mode].get('kind')!='cinematic':
                        value*=float(position>=seam+length*.5) if incoming else float(position<seam+length*.5)
                    elif mode in transition_graphics.PRESETS or mode=='crossfade' or mode.startswith('zoom_'):
                        p=easing_value((position-seam)/length,'ease_in_out')
                        value*=p if incoming else 1-p
                if fade_in:value*=easing_value((t+elapsed)/fade_in,easing)
                if fade_out:value*=easing_value((clip_length-t-elapsed)/fade_out,easing)
                return value
            initial=frame_alpha(0)
            last=initial;commands=[]
            for frame in range(1,math.ceil(end*fps)):
                value=frame_alpha(frame)
                if abs(value-last)>1e-7:
                    commands.append(f'{max(0,frame/fps-0.000001):.6f} {target} aa {value:.8f};')
                    last=value
            if commands:
                command_path=work/f'scene-{index:04d}-alpha-{layer_index:03d}.txt'
                command_path.write_text('\n'.join(commands),encoding='utf-8')
                safe_path=str(command_path).replace('\\','\\\\').replace(':','\\:').replace("'","\\'")
                overlay_filters.append(f"sendcmd=f='{safe_path}'")
            overlay_filters.append(f'{target}=aa={initial:.8f}')
        elif animated_opacity or fade_in or fade_out or layer.get('join_in') or layer.get('join_out') or lag:
            overlay_filters.append(f"geq=r='r(X\\,Y)':g='g(X\\,Y)':b='b(X\\,Y)':a='alpha(X\\,Y)*({alpha_expr})'")
        else:
            overlay_filters.append(f"colorchannelmixer=aa={opacity:.4f}")
        # Apply alpha at a fixed size: geq in FFmpeg 9 can crash when its input
        # dimensions change on each frame. Scaling afterward preserves alpha.
        if any("scale" in point for point in keyframes) or scale != 1 or any(layer.get('join_'+key,{}).get('type','').startswith('zoom_') for key in ('in','out')):
            overlay_filters.append(f"scale=w='max(2\\,iw*({scale_expr}))':h='max(2\\,ih*({scale_expr}))':eval=frame")
        overlay_filters.extend([f"tpad=stop_mode=clone:stop_duration={end:.6f}", f"trim=duration={end:.6f}", f"setpts=PTS-STARTPTS[{overlay_label}]"])
        filters.append(",".join(overlay_filters))
        next_label = f"v{layer_index + 1}"
        filters.append(f"[{current}][{overlay_label}]overlay=x='{x_expr}':y='{y_expr}':eval=frame:enable='between(t\\,{start:.6f}\\,{end:.6f})'[{next_label}]")
        current = next_label
    hardware = hardware_export(width, height, fps)
    if hardware:
        # A single color range is essential when scene files are joined: the
        # container retains the first scene's HEVC parameters for all scenes.
        filters.append(f"[{current}]scale=in_range=auto:out_range=tv[stable_output]")
        current = "stable_output"
    cmd += (["-filter_complex", ";".join(filters), "-map", f"[{current}]", "-an",
             "-t", f"{duration:.6f}", "-r", str(fps)]
            + video_encoder_options(hardware) + ["-movflags", "+faststart", str(output)])
    run_ffmpeg(cmd, "scene", index=index)


def transitions(scenes: list[dict]) -> list[tuple[str, float]]:
    result = []
    for i, scene in enumerate(scenes[:-1]):
        transition = scene.get("transition_out", scene.get("transition", {"type": "cut"}))
        if isinstance(transition, str):
            transition = {"type": transition}
        if not isinstance(transition, dict):
            raise ValueError(f"scene {i+1} transition must be an object")
        name = str(transition.get("type", "cut")).lower()
        if name in {"none", "hard", "instant"}:
            name = "cut"
        if name in {"dissolve", "fade"}:
            name = "crossfade"
        if name == "wipe":
            name = "swipe"
        if name not in {"cut", "crossfade", "swipe"}:
            raise ValueError(f"scene {i+1} transition {name} is not supported")
        duration = number(transition.get("duration", 0.35 if name == "crossfade" else 0), "transition duration")
        if name == "cut":
            duration = 0
        else:
            left = number(scene.get("duration", scene.get("length")), "scene duration")
            right = number(scenes[i + 1].get("duration", scenes[i + 1].get("length")), "scene duration")
            if duration <= 0 or duration >= min(left, right):
                raise ValueError(f"scene {i+1} transition must fit both adjacent scenes")
        result.append((name, duration))
    return result


def normalize_audio(project: dict, project_file: Path) -> list[dict]:
    tracks = project.get("tracks") or []
    if isinstance(tracks, dict):
        tracks = [{"kind": kind, **value} for kind, value in tracks.items() if isinstance(value, dict)]
    if not isinstance(tracks, list):
        raise ValueError("tracks must be an array or object")
    for kind in ("voice", "music"):
        if isinstance(project.get(kind), dict):
            tracks.append({"kind": kind, **project[kind]})
    result = []
    for index, track in enumerate(tracks):
        if not isinstance(track, dict):
            raise ValueError(f"audio track {index} must be an object")
        if not source_value(track):
            continue
        source = resolve_source(source_value(track), project_file, f"audio track {index}")
        data = probe(source)
        if not any(stream.get("codec_type") == "audio" for stream in data.get("streams", [])):
            raise ValueError(f"audio track {index} has no audio stream")
        volume = number(track.get("volume", 1), "audio volume")
        if volume > 5:
            raise ValueError("audio volume exceeds allowed range 0..5")
        start = number(track.get("start", 0), "audio start")
        trim_start = number(track.get("trim_start", 0), "audio trim start")
        clip_duration = track.get("duration")
        if clip_duration is not None:
            clip_duration = number(clip_duration, "audio duration", 0.01)
        loop = bool(track.get("loop", False))
        available = media_duration(source)
        if available and not loop and clip_duration is not None and trim_start + clip_duration > available + 0.05:
            raise ValueError(f"audio track {index} ends beyond its source")
        result.append({"path": source, "kind": track.get("kind", "audio"), "volume": volume, "start": start, "trim_start": trim_start, "duration": clip_duration, "loop": loop})
    return result


def run_ffmpeg(cmd: list[str], stage: str, index: int | None = None, duration: float | None = None) -> None:
    if not FFMPEG:
        raise RuntimeError("ffmpeg is not installed")
    # FFmpeg diagnostic output can include paths; keep it out of normal progress.
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as error_file:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=error_file, text=True)
        try:
            for line in process.stdout:
                line = line.strip()
                if duration and line.startswith("out_time_us="):
                    try:
                        progress = min(1, max(0, int(line.split("=", 1)[1]) / 1_000_000 / duration))
                        emit(stage, progress=round(progress, 4), **({"scene": index} if index is not None else {}))
                    except ValueError:
                        pass
            returncode = process.wait()
        except KeyboardInterrupt:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            raise
        finally:
            process.stdout.close()
        if returncode:
            error_file.seek(0)
            diagnostic = error_file.read()[-3000:].strip()
            reason = diagnostic or (f"terminated by signal {-returncode}" if returncode < 0 else f"exit code {returncode}")
            raise RuntimeError(f"ffmpeg {stage} failed: {reason}")


def compose(project: dict, project_file: Path, segments: list[Path], output: Path, expected_duration: float) -> None:
    scenes = project["scenes"]
    changes = transitions(scenes)
    width = int(project.get("width", (project.get("resolution") or {}).get("width", 1920)))
    height = int(project.get("height", (project.get("resolution") or {}).get("height", 1080)))
    fps = int(project.get("fps", 30))
    audio_tracks = normalize_audio(project, project_file)
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    for segment in segments:
        cmd += ["-i", str(segment)]
    for track in audio_tracks:
        if track["loop"]:
            cmd += ["-stream_loop", "-1"]
        if track["trim_start"]:
            cmd += ["-ss", f"{track['trim_start']:.6f}"]
        cmd += ["-i", str(track["path"])]
    cmd += ["-f", "lavfi", "-t", f"{expected_duration:.6f}", "-i", "anullsrc=r=48000:cl=stereo"]
    filters = []
    current = "0:v"
    running_duration = number(scenes[0].get("duration", scenes[0].get("length")), "scene duration")
    for i, (name, duration) in enumerate(changes, 1):
        label = f"joined{i}"
        if name == "cut":
            filters.append(f"[{current}][{i}:v]concat=n=2:v=1:a=0[{label}]")
        else:
            offset = running_duration - duration
            effect = "wipeleft" if name == "swipe" else "fade"
            filters.append(f"[{current}][{i}:v]xfade=transition={effect}:duration={duration:.6f}:offset={offset:.6f}[{label}]")
        running_duration += number(scenes[i].get("duration", scenes[i].get("length")), "scene duration") - duration
        current = label
    if not changes:
        filters.append("[0:v]null[joined0]")
        current = "joined0"
    audio_labels = []
    for i, track in enumerate(audio_tracks, len(segments)):
        label = f"aud{i}"
        delay = int(round(track["start"] * 1000))
        clip_trim = f",atrim=duration={track['duration']:.6f}" if track["duration"] is not None else ""
        filters.append(f"[{i}:a]aresample=48000{clip_trim},volume={track['volume']:.6f},adelay={delay}|{delay},atrim=duration={expected_duration:.6f},asetpts=PTS-STARTPTS[{label}]")
        audio_labels.append(label)
    silence_index = len(segments) + len(audio_tracks)
    audio_labels.append(f"{silence_index}:a")
    if len(audio_labels) > 1:
        filters.append("".join(f"[{label}]" for label in audio_labels) + f"amix=inputs={len(audio_labels)}:duration=longest:dropout_transition=0:normalize=0,atrim=duration={expected_duration:.6f}[mix]")
    else:
        filters.append(f"[{audio_labels[0]}]atrim=duration={expected_duration:.6f}[mix]")
    hardware = hardware_export(width, height, fps)
    if hardware:
        filters.append(f"[{current}]scale=in_range=auto:out_range=tv[stable_output]")
        current = "stable_output"
    cmd += (["-filter_complex", ";".join(filters), "-map", f"[{current}]", "-map", "[mix]",
             "-t", f"{expected_duration:.6f}", "-r", str(fps)]
            + video_encoder_options(hardware) + ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(output)])
    run_ffmpeg(cmd, "compose", duration=expected_duration)


def timeline_transitions(on_layer: list[dict], fps: int) -> None:
    on_layer.sort(key=lambda item: (item["start"], item["clip_order"]))
    for previous, following in zip(on_layer, on_layer[1:]):
        transition = previous.get("transition") or {"type": "cut"}
        if isinstance(transition, str):
            transition = {"type": transition}
        if not isinstance(transition, dict):
            raise ValueError("clip transition must be an object")
        name = str(transition.get("type", "cut")).lower()
        if name in {"none", "hard", "instant"}:
            name = "cut"
        if name in {"fade", "dissolve"}:
            name = "crossfade"
        if name in {"wipe"}:
            name = "swipe"
        if name not in {"cut", "crossfade", "swipe"}:
            raise ValueError(f"Unsupported timeline transition: {name}")
        if name == "cut":
            continue
        transition_duration = number(transition.get("duration", .35), "transition duration", .01)
        if transition_duration > min(previous["duration"], following["duration"]):
            raise ValueError("Transition is longer than an adjacent clip")
        overlap = previous["end"] - following["start"]
        if overlap >= transition_duration - 1 / fps:
            following["fade_in" if name == "crossfade" else "slide_in"] = transition_duration
        elif abs(overlap) <= 1 / fps:
            previous["fade_out" if name == "crossfade" else "slide_out"] = transition_duration
            following["fade_in" if name == "crossfade" else "slide_in"] = transition_duration
        else:
            raise ValueError("Transition needs touching clips or a full overlap of its duration")


def frame_index(seconds: float, fps: int) -> int:
    return math.floor(seconds * fps + .5 + 1e-8)


def timeline_plan(project: dict, project_file: Path, width: int, height: int, fps: int) -> tuple[list[dict], list[dict], float]:
    """Normalize the independent universal tracks into visual and audio clips."""
    layers = project.get("timeline_layers")
    if not isinstance(layers, list) or not layers:
        raise ValueError("timeline_layers must contain at least one layer")
    if any(not isinstance(layer, dict) for layer in layers):
        raise ValueError("timeline layers must be objects")
    visual, audio = [], []
    ordered_layers = sorted(enumerate(layers), key=lambda pair: (number(pair[1].get("z", pair[1].get("z_index", pair[0])), "layer z", -100000), pair[0]))
    for layer_order, (_, layer) in enumerate(ordered_layers):
        if not isinstance(layer, dict) or not isinstance(layer.get("clips"), list):
            raise ValueError("Each timeline layer needs a clips array")
        on_layer = []
        for clip_order, clip in enumerate(layer["clips"]):
            if not isinstance(clip, dict):
                raise ValueError("timeline clip must be an object")
            kind = str(clip.get("type", clip.get("kind", ""))).lower()
            if kind not in {"video", "image", "text", "animation", "audio"}:
                raise ValueError(f"Unsupported timeline clip type: {kind}")
            animation_kind = animation_content_kind(clip) if kind == "animation" else None
            if kind == "audio":
                start = number(clip.get("start", 0), "clip start")
                duration = number(clip.get("duration"), "clip duration", .01)
            else:
                raw_start = number(clip.get("start", 0), "clip start")
                raw_duration = number(clip.get("duration"), "clip duration", 1 / fps)
                start_frames = frame_index(raw_start, fps)
                duration_frames = frame_index(raw_start + raw_duration, fps) - start_frames
                if duration_frames < 1:
                    raise ValueError("clip duration must include at least one frame")
                start, duration = start_frames / fps, duration_frames / fps
            trim_start = number(clip.get("trim_start", 0), "clip trim_start")
            record = {**clip, "type": kind, "start": start, "duration": duration, "end": start + duration, "fps":fps,
                      "trim_start": trim_start, "layer_order": layer_order, "clip_order": clip_order}
            for direction in ('in','out'):
                if clip.get('join_'+direction):
                    join=clip['join_'+direction];first=frame_index(join['seam'],fps);last=frame_index(join['seam']+join['duration'],fps)
                    record['join_'+direction]={**join,'seam':first/fps,'duration':max(1,last-first)/fps}
            source = source_value(clip)
            if kind in {"video", "image", "audio"} or animation_kind in {"image", "video"}:
                path = resolve_source(source, project_file, f"timeline clip {clip.get('id', clip_order)}")
                record["source"] = str(path)
                info = probe(path)
                stream_types = {stream.get("codec_type") for stream in info.get("streams", [])}
                if kind == "audio" and "audio" not in stream_types:
                    raise ValueError(f"Audio clip has no audio stream: {path.name}")
                if kind != "audio" and "video" not in stream_types:
                    raise ValueError(f"Visual clip has no image/video stream: {path.name}")
                if kind == "video" or animation_kind == "video":
                    available = media_duration(path)
                    if available and trim_start + duration > available + 1 / fps:
                        raise ValueError(f"Timeline video ends before clip: {path.name}")
                if kind == "audio":
                    available = media_duration(path)
                    if available and trim_start + duration > available + .05:
                        raise ValueError(f"Timeline audio ends before clip: {path.name}")
                if kind == "audio" or (kind == "video" and "audio" in stream_types):
                    volume = number(clip.get("volume", 0 if kind == "video" else 1), "clip volume")
                    if volume > 5:
                        raise ValueError("clip volume exceeds allowed range 0..5")
                    if volume:
                        audio.append({"kind": kind, "source": str(path), "volume": volume, "start": start,
                                      "trim_start": trim_start, "duration": duration})
            elif kind == "text" or animation_kind == "text":
                if not str(clip.get("text", "")).strip():
                    raise ValueError("Text clip has no text")
            keyframes = clip.get("keyframes") or []
            if not isinstance(keyframes, list):
                raise ValueError("clip keyframes must be an array")
            keyframes = [dict(point) if isinstance(point, dict) else point for point in keyframes]
            for point in keyframes:
                if not isinstance(point, dict):
                    raise ValueError("clip keyframes must contain objects")
                number(point.get("time"), "keyframe time")
            preset = str(clip.get("preset") or "none").lower()
            record["easing"] = str(clip.get("easing", "linear"))
            easing_expr("0.5", record["easing"])
            preset_duration = min(duration, number(clip.get("preset_duration", .4), "preset duration", .01))
            if preset in {"fade_in", "fade_out", "slide_in", "slide_out"}:
                record[preset] = preset_duration
            elif preset in {"zoom_in", "pop"}:
                if not any("scale" in point for point in keyframes):
                    if preset == "zoom_in":
                        keyframes.extend([{"time": 0, "scale": .8}, {"time": preset_duration, "scale": 1}])
                    else:
                        keyframes.extend([{"time": 0, "scale": .7}, {"time": preset_duration / 2, "scale": 1.12},
                                          {"time": preset_duration, "scale": 1}])
                record["fade_in"] = min(preset_duration / 2, duration)
            elif preset != "none":
                raise ValueError(f"Unsupported animation preset: {preset}")
            record["keyframes"] = keyframes
            scalar_expr(keyframes, "scale", number(clip.get("scale", 1), "clip scale", 0.05), 0.05, 8, "t")
            scalar_expr(keyframes, "opacity", number(clip.get("opacity", 1), "clip opacity"), 0, 1, "t")
            if kind == "audio":
                continue
            visual.append(record)
            on_layer.append(record)
        if project.get("layer_mode") != "item":
            timeline_transitions(on_layer, fps)
    if project.get("layer_mode") == "item":
        timeline_transitions(visual, fps)
    if not visual and not audio:
        raise ValueError("Timeline is empty")
    total = max((clip["end"] for clip in visual), default=0)
    total = max(total, *(track["start"] + track["duration"] for track in audio)) if audio else total
    total = math.ceil(total * fps - 1e-8) / fps
    if total <= 0:
        raise ValueError("Timeline has no duration")
    # Spoken audio keeps its real timestamps. Its fractional final sample can
    # require one more output frame than the rounded visual boundary. Keep the
    # final composition visible through that frame instead of rendering an
    # empty background. Interior edit boundaries and longer gaps stay intact.
    visual_end=max((clip['end'] for clip in visual),default=0)
    if visual and 1e-8<total-visual_end<=1/fps+1e-8:
        for clip in visual:
            if abs(clip['end']-visual_end)<1e-8:
                clip['end']=total
                clip['duration']=total-clip['start']
    background = str(project.get("background", "#101114"))
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", background):
        raise ValueError("Invalid timeline background color")
    return visual, audio, total


def timeline_segments(visual: list[dict], total: float, fps: int) -> list[tuple[float, float, list[dict]]]:
    boundaries = sorted({0, round(total * fps), *(round(clip["start"] * fps) for clip in visual),
                          *(round(clip["end"] * fps) for clip in visual)})
    if len(boundaries) > 2001:
        raise ValueError("Timeline has more than 2000 visual boundaries")
    result = []
    for first, last in zip(boundaries, boundaries[1:]):
        if last <= first:
            continue
        start, end = first / fps, last / fps
        active = [clip for clip in visual if clip["start"] < end - 1e-8 and clip["end"] > start + 1e-8]
        active.sort(key=lambda clip: (clip["layer_order"], clip["start"], clip["clip_order"]))
        result.append((start, end, active))
    return result


def make_shape(clip: dict, work: Path) -> Path:
    try:
        color = ImageColor.getrgb(str(clip.get("color", "#ffffff")))
    except ValueError as exc:
        raise ValueError("Animation shape has invalid color") from exc
    path = work / f"shape-{clip['layer_order']}-{clip['clip_order']}.png"
    if not path.exists():
        Image.new("RGBA", (4, 4), (*color, 255)).save(path)
    return path


def timed_text_units(clip,width):
    words=clip['text_words']
    if not (clip.get('word_entrance') or {}).get('type','').startswith('letters_'):return words
    font=ImageFont.truetype(str(first_font(clip.get('font_family','Golos'),clip.get('font_weight',400))),int(clip.get('font_size',54)))
    try:font.set_variation_by_axes([float(clip.get('font_weight',400)) if b'Weight' in a['name'] else a['default'] for a in font.get_variation_axes()])
    except (OSError,AttributeError):pass
    units=[];box_width=width*float(clip.get('width',1))
    for i,word in enumerate(words):
        text=word['text'];left=word['x']-font.getlength(text)/box_width/2
        finish=word.get('end',words[i+1]['start'] if i+1<len(words) else word['start']+.25)
        spread=min(.24,max(.04,finish-word['start'])*.7)
        for j,char in enumerate(text):
            before=font.getlength(text[:j]);after=font.getlength(text[:j+1])
            units.append({**word,'text':char,'x':left+(before+after)/2/box_width,'width':(after-before+12)/box_width,'start':word['start']+spread*j/max(1,len(text)-1)})
    return units

def timeline_scene(start: float, end: float, active: list[dict], work: Path, width: int, height: int, background: str) -> dict:
    scene = {"type": "color", "color": background, "duration": end - start, "layers": []}
    for clip in active:
        elapsed = max(0, start - clip["start"])
        kind = clip["type"]
        shape = kind == "animation" and animation_content_kind(clip) == "shape"
        gradient = kind == "animation" and animation_content_kind(clip) == "gradient"
        graphic = kind == "animation" and animation_content_kind(clip) == "graphic_transition"
        if kind == "animation":
            kind = "video" if gradient or graphic else "image" if shape else animation_content_kind(clip)
        normalized = str(clip.get("units", "normalized")).lower() != "px"
        if normalized:
            clip_width = max(1, round(number(clip.get("width", 1), "clip width", .01) * width))
            clip_height = max(1, round(number(clip.get("height", 1), "clip height", .01) * height))
            center_x = number(clip.get("x", .5), "clip x", -8)
            center_y = number(clip.get("y", .5), "clip y", -8)
            layer_x = center_x if kind == "text" else center_x * width - clip_width / 2
            layer_y = center_y if kind == "text" else center_y * height - clip_height / 2
            points = []
            for point in clip.get("keyframes") or []:
                adjusted = dict(point)
                if kind != "text":
                    if "x" in adjusted:
                        adjusted["x"] = number(adjusted["x"], "keyframe x", -8) * width - clip_width / 2
                    if "y" in adjusted:
                        adjusted["y"] = number(adjusted["y"], "keyframe y", -8) * height - clip_height / 2
                points.append(adjusted)
        else:
            clip_width = dimension(clip.get("width"), width, width)
            clip_height = dimension(clip.get("height"), height, height)
            layer_x = number(clip.get("x", 0), "clip x", -width * 8)
            layer_y = number(clip.get("y", 0), "clip y", -height * 8)
            points = clip.get("keyframes") or []
        layer = {"type": kind, "start": 0, "duration": end - start,
                 "keyframe_offset": elapsed, "clip_duration": clip["duration"],
                 "keyframes": points, "opacity": clip.get("opacity", 1), "easing": clip.get("easing", "linear"),
                 "scale": clip.get("scale", 1), "fade_in": clip.get("fade_in", 0),
                 "fade_out": clip.get("fade_out", 0), "slide_in": clip.get("slide_in", 0),
                 "slide_out": clip.get("slide_out", 0), "x": layer_x, "y": layer_y,
                 "width": clip_width, "height": clip_height,
                 "position_units": "normalized" if normalized and kind == "text" else "pixels"}
        if shape:
            layer["stretch"] = True
        layer['scale_anchor']='center'
        layer['global_offset']=start
        for key in ('join_in','join_out'):
            if key not in clip:continue
            join=clip[key]
            # Ignore transition envelopes that are already constant in this slice.
            if key=='join_in' and start >= float(join['seam'])+float(join['duration'])-1e-8:continue
            if key=='join_out' and end <= float(join['seam'])+1e-8:continue
            layer[key]=join
        opacity_points=[p for p in layer['keyframes'] if 'opacity' in p]
        opacity_at_start=scalar_value(layer['keyframes'],'opacity',float(layer['opacity']),elapsed,layer['easing']) if opacity_points else None
        opacity_at_end=scalar_value(layer['keyframes'],'opacity',float(layer['opacity']),elapsed+end-start,layer['easing']) if opacity_points else None
        constant_opacity = opacity_points and abs(opacity_at_start-opacity_at_end)<1e-9 and all(
            abs(float(point['opacity'])-opacity_at_start)<1e-9
            for point in opacity_points if elapsed<float(point['time'])<elapsed+end-start)
        always_constant = opacity_points and all(abs(float(point['opacity'])-float(layer['opacity']))<1e-9 for point in opacity_points)
        if always_constant or (constant_opacity and os.environ.get('MULTIBOT_FAST_ALPHA','1')!='0'):
            layer['opacity']=opacity_at_start
            layer['keyframes']=[{k:v for k,v in point.items() if k!='opacity'} for point in layer['keyframes']]
        for key in ('mask','corner_radius','shadow','font_family','font_weight','text_align','line_height','blur','motion_blur','visual_effect'):
            if key in clip:layer[key]=clip[key]
        effect=visual_effects.PRESETS.get(clip.get('visual_effect'),{})
        if effect.get('blur'):layer['blur']=float(layer.get('blur',0))+effect['blur']
        if effect.get('shadow'):layer['shadow']=effect['shadow']
        # A static, opaque shape covering the whole canvas is already the
        # scene background. Avoid scaling and compositing it for every frame.
        if (os.environ.get('MULTIBOT_FAST_BACKGROUND','1')!='0' and shape and not scene['layers']
            and layer['x']==0 and layer['y']==0 and layer['width']==width and layer['height']==height
            and layer['scale']==1 and layer['opacity']==1 and not layer['keyframes']
            and not layer.get('join_in') and not layer.get('join_out')
            and not any(layer.get(k) for k in ('fade_in','fade_out','slide_in','slide_out','blur','shadow','motion_blur','visual_effect'))
            and layer.get('mask','none') in (None,'none')
            and re.fullmatch(r'#[0-9a-fA-F]{6}',str(clip.get('color','')))):
            scene['color']=clip['color']
            continue
        if kind == "text":
            layer.update({"text": clip.get("text", ""), "color": clip.get("color", "white"),
                          "font_size": clip.get("font_size", 54)})
        else:
            layer["source"] = str(transition_graphics.video(clip['graphic_style'],clip['duration'],clip.get('fps',30),width,height,work)) if graphic else str(gradient_background.video(clip['gradient'],clip['duration'],clip.get('fps',30),work)) if gradient else clip.get("source") or str(make_shape(clip, work))
            if kind == "video":
                layer["trim_start"] = clip["trim_start"] + elapsed
        if kind == "text" and clip.get("text_words"):
            for word in timed_text_units(clip,width):
                reveal = max(0, float(word["start"]) - elapsed)
                if reveal >= end - start:
                    continue
                word_layer={**layer, "text": word["text"], "start": reveal,
                    "duration": end - start - reveal, "x": layer_x + (word["x"] - .5) * float(clip.get("width", 1)),
                    "y": layer_y + (word["y"] - .5) * float(clip.get("height", 1)),
                    "width": max(1, round(word["width"] * clip_width)), "height": max(1, round(word["height"] * clip_height)),
                    "keyframes": [], "font_size": clip.get("font_size", 54)}
                effect=clip.get('word_entrance')
                if effect:
                    mode=effect['type'].replace('letters_','');distance=effect['distance'];x,y=word_layer['x'],word_layer['y'];dx=-distance/width if mode=='left' else distance/width if mode=='right' else 0;dy=distance/height if mode in {'up','blur_up'} else -distance/height if mode=='down' else 0
                    scale=.82 if mode=='pop' else .88 if mode=='grow' else 1.1 if mode=='shrink' else 1
                    points=[dict(time=word['start'],x=x+dx,y=y+dy,scale=scale,opacity=0)]
                    if mode=='pop':points.append(dict(time=word['start']+effect['duration']*.66,x=x,y=y,scale=1.04,opacity=1))
                    points.append(dict(time=word['start']+effect['duration'],x=x,y=y,scale=1,opacity=1))
                    word_layer['keyframes']=points;word_layer['easing']='ease_out'
                    if 'blur' in mode:
                        blur={**word_layer,'raster_blur':6,'keyframes':[dict(points[0]),dict(time=word['start']+effect['duration']*.3,x=x+dx*.34,y=y+dy*.34,scale=1,opacity=.65),dict(points[-1],opacity=0)]}
                        scene['layers'].append(blur)
                scene['layers'].append(word_layer)
        else:
            scene["layers"].append(layer)
    return scene


def compose_timeline(segments: list[Path], tracks: list[dict], output: Path, work: Path, total: float) -> None:
    """Concatenation keeps the input count small even for a long timeline."""
    listing = work / "segments.txt"
    listing.write_text("".join("file '" + str(path).replace("'", "'\\''") + "'\n" for path in segments), encoding="utf-8")
    joined = work / "joined.mp4"
    run_ffmpeg([FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                "-i", str(listing), "-c:v", "copy", "-an", str(joined)], "join")
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(joined)]
    for track in tracks:
        if track.get("loop"):
            cmd += ["-stream_loop", "-1"]
        if track["trim_start"]:
            cmd += ["-ss", f"{track['trim_start']:.6f}"]
        cmd += ["-i", str(track["source"])]
    cmd += ["-f", "lavfi", "-t", f"{total:.6f}", "-i", "anullsrc=r=48000:cl=stereo"]
    filters, labels = [], []
    for index, track in enumerate(tracks, 1):
        label = f"audio{index}"
        delay = round(track["start"] * 1000)
        filters.append(f"[{index}:a]aresample=48000,atrim=duration={track['duration']:.6f},volume={track['volume']:.6f},adelay={delay}|{delay},atrim=duration={total:.6f},asetpts=PTS-STARTPTS[{label}]")
        labels.append(label)
    labels.append(f"{len(tracks) + 1}:a")
    filters.append("".join(f"[{label}]" for label in labels) + f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,atrim=duration={total:.6f}[mix]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[mix]", "-t", f"{total:.6f}",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(output)]
    run_ffmpeg(cmd, "compose", duration=total)


def validate_project(project: dict, project_file: Path) -> tuple[int, int, int, float]:
    if not isinstance(project, dict):
        raise ValueError("Project JSON must be an object")
    scenes = project.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Project needs at least one scene")
    if len(scenes) > 2000:
        raise ValueError("Project has too many scenes")
    resolution = project.get("resolution") or {}
    width = int(number(project.get("width", resolution.get("width", 1920)), "width", 160))
    height = int(number(project.get("height", resolution.get("height", 1080)), "height", 90))
    fps = int(number(project.get("fps", 30), "fps", 1))
    if width > 7680 or height > 4320 or fps > 120 or width % 2 or height % 2:
        raise ValueError("Resolution must have even dimensions and be at most 7680x4320; fps <= 120")
    total = 0.0
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise ValueError(f"scene {index} must be an object")
        kind = normalized_kind(scene)
        duration = number(scene.get("duration", scene.get("length")), f"scene {index} duration", 0.04)
        total += duration
        if kind in {"image", "video"}:
            source = resolve_source(source_value(scene), project_file, f"scene {index}")
            if kind == "video":
                trim_start = number(scene.get("trim_start", scene.get("source_start", scene.get("offset", 0))), "trim_start")
                available = media_duration(source)
                if available and trim_start + duration > available + 1 / fps:
                    raise ValueError(f"scene {index} video source ends before the planned scene")
        for layer in scene.get("layers") or []:
            if not isinstance(layer, dict):
                raise ValueError(f"scene {index} has invalid layer")
            layer_kind = normalized_kind(layer)
            if layer_kind in {"image", "video"}:
                resolve_source(source_value(layer), project_file, f"scene {index} layer")
    for _, overlap in transitions(scenes):
        total -= overlap
    normalize_audio(project, project_file)
    if total <= 0:
        raise ValueError("Project has no duration")
    return width, height, fps, total


def verify_output_streams(info: dict, expected_duration: float, fps: int) -> None:
    streams=info.get('streams',[])
    video=next((s for s in streams if s.get('codec_type')=='video'),None)
    audio=next((s for s in streams if s.get('codec_type')=='audio'),None)
    if not video or not audio:
        raise RuntimeError('Rendered file lacks a video or audio stream')
    tolerance=max(.08,2/fps)
    for label,stream in (('video',video),('audio',audio)):
        try:stream_duration=float(stream.get('duration'))
        except (TypeError,ValueError):continue
        if abs(stream_duration-expected_duration)>tolerance:
            raise RuntimeError(f'Rendered {label} duration differs: expected {expected_duration:.3f}, got {stream_duration:.3f}')
    try:frames=int(video.get('nb_frames'))
    except (TypeError,ValueError):frames=None
    expected_frames=frame_index(expected_duration,fps)
    if frames is not None and abs(frames-expected_frames)>1:
        raise RuntimeError(f'Rendered video frame count differs: expected {expected_frames}, got {frames}')


def render(project_file: Path, output: Path, validate_only: bool = False) -> dict:
    project_file = project_file.expanduser().resolve()
    if not project_file.is_file():
        raise ValueError(f"Project JSON not found: {project_file}")
    project = json.loads(project_file.read_text(encoding="utf-8"))
    prepare_cloud_sources(offline_sources(project,project_file),validate_only=validate_only)
    universal = "timeline_layers" in project
    if universal:
        resolution = project.get("resolution") or {}
        width = int(number(project.get("width", resolution.get("width", 1920)), "width", 160))
        height = int(number(project.get("height", resolution.get("height", 1080)), "height", 90))
        fps = int(number(project.get("fps", 30), "fps", 1))
        if width > 7680 or height > 4320 or fps > 120 or width % 2 or height % 2:
            raise ValueError("Resolution must have even dimensions and be at most 7680x4320; fps <= 120")
        visual, audio, total = timeline_plan(project, project_file, width, height, fps)
        slices = timeline_segments(visual, total, fps)
        summary = {"duration": round(total, 3), "width": width, "height": height, "fps": fps,
                   "scenes": len(slices), "clips": sum(len(layer["clips"]) for layer in project["timeline_layers"])}
    else:
        width, height, fps, total = validate_project(project, project_file)
        summary = {"duration": round(total, 3), "width": width, "height": height, "fps": fps, "scenes": len(project["scenes"])}
    emit("validated", **summary)
    if validate_only:
        return summary
    if universal:
        import gpu_export
        if gpu_export.available(project, width, height, fps):
            try:
                emit('gpu_start')
                return gpu_export.render_gpu(sys.modules[__name__], project_file, output, project,
                                             width, height, fps, total)
            except Exception as error:
                # The established renderer remains available if GPU setup,
                # media decoding or verification fails. Cancellation raises
                # KeyboardInterrupt and is never converted into a retry.
                emit('gpu_fallback', message=str(error))
    # Probe before launching concurrent scene workers so every segment uses
    # the same codec and the same parameter set.
    hardware_export(width, height, fps)
    output = output.expanduser().resolve()
    if output.suffix.lower() != ".mp4":
        raise ValueError("Output file must end in .mp4")
    if output == project_file:
        raise ValueError("Output cannot replace the project manifest")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    with tempfile.TemporaryDirectory(prefix="mbvs-render-") as tmp:
        work = Path(tmp)
        segments = []
        if universal:
            # Prepare each slice when needed so long projects show progress
            # while their later transitions and backgrounds are prepared.
            scenes_to_render = slices
        else:
            scenes_to_render = project["scenes"]
        # Independent segments can render concurrently. Prepare shared
        # transition assets on the main thread and isolate each worker's
        # raster cache, avoiding concurrent writes to the same temporary file.
        completed = {}
        next_index = 0
        completed_duration = 0.0
        workers, _ = render_parallelism(width, height, fps)
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='studio-render') as pool:
            pending = {}
            def submit_next():
                nonlocal next_index
                if next_index >= len(scenes_to_render):
                    return False
                item = scenes_to_render[next_index]
                index = next_index + 1
                next_index += 1
                scene = (timeline_scene(*item, work, width, height, project.get("background", "#101114"))
                         if universal else item)
                segment = work / f"scene-{index:04d}.mp4"
                scene_work = work / f"scene-work-{index:04d}"
                scene_work.mkdir()
                emit("scene_start", scene=index, total=len(scenes_to_render))
                future = pool.submit(render_scene, scene, project_file, segment, scene_work, width, height, fps, index)
                pending[future] = (index, item, segment)
                return True
            while len(pending) < workers and submit_next():
                pass
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    index, item, segment = pending.pop(future)
                    try:
                        future.result()
                    except Exception as exc:
                        raise RuntimeError(f"Сцена {index}: {exc}") from exc
                    completed[index] = segment
                    if universal:
                        completed_duration += item[1]-item[0]
                        emit("scene_done", scene=index, total=len(scenes_to_render), rendered_duration=completed_duration, total_duration=total)
                    else:
                        emit("scene_done", scene=index, total=len(scenes_to_render), completed=len(completed))
                while len(pending) < workers and submit_next():
                    pass
        segments = [completed[index] for index in range(1, len(scenes_to_render)+1)]
        temporary_output = output.parent / f".{output.stem}.render-{os.getpid()}-{secrets.token_hex(4)}.mp4"
        try:
            if universal:
                compose_timeline(segments, audio, temporary_output, work, total)
            else:
                compose(project, project_file, segments, temporary_output, total)
            info = probe(temporary_output)
            verify_output_streams(info,total,fps)
            actual = media_duration(temporary_output)
            if abs(actual - total) > max(0.5, 2 / fps):
                raise RuntimeError(f"Rendered duration differs: expected {total:.3f}, got {actual:.3f}")
            # Decode the result once. Metadata alone is not a quality check.
            emit('verify',progress=0)
            run_ffmpeg([FFMPEG, "-nostdin", "-v", "error", "-xerror", "-i", str(temporary_output),
                        "-progress", "pipe:1", "-nostats", "-f", "null", "-"], "verify", duration=total)
            # Publish without clobbering a result created by another render job.
            os.link(temporary_output, output)
        finally:
            temporary_output.unlink(missing_ok=True)
    emit("complete", output=str(output), **summary)
    return summary


def main() -> None:
    def request_cancel(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, request_cancel)
    parser = argparse.ArgumentParser(description="Render a MultiBot Video Studio project to MP4")
    parser.add_argument("project_pos", nargs="?", type=Path)
    parser.add_argument("output_pos", nargs="?", type=Path)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    project_file = args.project or args.project_pos
    output = args.output or args.output_pos
    if not project_file or (not output and not args.validate_only):
        parser.error("Provide --project and --output")
    try:
        render(project_file, output or Path("unused.mp4"), args.validate_only)
    except KeyboardInterrupt:
        fail("Render cancelled")
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
