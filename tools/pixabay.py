#!/usr/bin/env python3
"""Search Pixabay and save individually selected media for YouTube episodes."""

import argparse
import getpass
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
CACHE = Path(__file__).resolve().parent / ".pixabay-cache"
SERVICE = "pixabay-youtube-api"
LICENSE_URL = "https://pixabay.com/service/terms/"


def api_key():
    supplied = os.environ.get("PIXABAY_API_KEY", "").strip()
    if supplied:
        return supplied
    result = subprocess.run(
        ["security", "find-generic-password", "-a", getpass.getuser(), "-s", SERVICE, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode or not result.stdout.strip():
        raise RuntimeError("Pixabay API key is not available in macOS Keychain")
    return result.stdout.strip()


def api_get(kind, **params):
    endpoint = "https://pixabay.com/api/videos/" if kind == "video" else "https://pixabay.com/api/"
    clean = {key: value for key, value in params.items() if value is not None}
    cache_id = hashlib.sha256((kind + json.dumps(clean, sort_keys=True)).encode()).hexdigest()
    cached = CACHE / f"{cache_id}.json"
    if cached.exists() and time.time() - cached.stat().st_mtime < 86400:
        return json.loads(cached.read_text(encoding="utf-8"))
    url = endpoint + "?" + urlencode({"key": api_key(), **clean})
    request = Request(url, headers={"User-Agent": "YouTube-Pixabay-Asset-Selector/1.0"})
    try:
        with urlopen(request, timeout=25) as response:
            data = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Pixabay API returned HTTP {error.code}") from None
    except URLError:
        raise RuntimeError("Pixabay API could not be reached") from None
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def summary(hit, kind):
    item = {
        "id": hit.get("id"),
        "kind": kind,
        "tags": hit.get("tags"),
        "author": hit.get("user"),
        "source_page": hit.get("pageURL"),
    }
    if kind == "video":
        item["duration_seconds"] = hit.get("duration")
        item["sizes"] = {
            name: f"{media.get('width')}x{media.get('height')}"
            for name, media in hit.get("videos", {}).items() if media.get("url")
        }
    else:
        item["available_image"] = "largeImageURL"
        if hit.get("fullHDURL"):
            item["available_image"] = "fullHDURL"
    return item


def episode_dir(raw):
    directory = Path(raw).expanduser().resolve()
    try:
        directory.relative_to(ROOT)
    except ValueError:
        raise RuntimeError("The destination must be inside the YouTube folder") from None
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def media_url(hit, kind, quality):
    if kind == "video":
        option = hit.get("videos", {}).get(quality, {})
        return option.get("url"), option.get("width"), option.get("height")
    field = "fullHDURL" if quality == "fullhd" else "largeImageURL"
    return hit.get(field), None, None


def download(kind, media_id, quality, destination):
    data = api_get(kind, id=media_id)
    hit = next((entry for entry in data.get("hits", []) if str(entry.get("id")) == str(media_id)), None)
    if not hit:
        raise RuntimeError("The selected Pixabay asset was not found")
    url, width, height = media_url(hit, kind, quality)
    if not url:
        raise RuntimeError("The selected size is unavailable for this asset")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"pixabay.com", "cdn.pixabay.com"}:
        raise RuntimeError("Pixabay returned an unexpected download host")
    directory = episode_dir(destination)
    extension = Path(parsed.path).suffix.lower() or (".mp4" if kind == "video" else ".jpg")
    if extension not in ({".mp4"} if kind == "video" else {".jpg", ".jpeg", ".png", ".webp"}):
        raise RuntimeError("Pixabay returned an unexpected media format")
    file_path = directory / f"pixabay_{kind}_{media_id}_{quality}{extension}"
    source_path = directory / f"pixabay_{kind}_{media_id}_{quality}.source.json"
    if file_path.exists() or source_path.exists():
        raise RuntimeError("This asset already exists in the destination folder")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".pixabay-", delete=False) as temp:
            temp_path = Path(temp.name)
            with urlopen(Request(url, headers={"User-Agent": "YouTube-Pixabay-Asset-Selector/1.0"}), timeout=60) as response:
                shutil.copyfileobj(response, temp)
        if temp_path.stat().st_size == 0:
            raise RuntimeError("The downloaded asset is empty")
        digest = hashlib.sha256(temp_path.read_bytes()).hexdigest()
        temp_path.replace(file_path)
    except HTTPError as error:
        raise RuntimeError(f"The media download returned HTTP {error.code}") from None
    except URLError:
        raise RuntimeError("The selected media could not be downloaded") from None
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
    record = {
        "local_file": str(file_path),
        "pixabay_id": hit.get("id"),
        "source_page": hit.get("pageURL"),
        "author": hit.get("user"),
        "tags": hit.get("tags"),
        "license_reference": LICENSE_URL,
        "download_url": url,
        "selected_quality": quality,
        "width": width,
        "height": height,
        "sha256": digest,
        "review_status": "candidate_requires_visual_review",
    }
    source_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description="Find and save selected Pixabay media for YouTube episodes")
    subcommands = parser.add_subparsers(dest="command", required=True)
    search = subcommands.add_parser("search", help="Find candidate images or videos")
    search.add_argument("kind", choices=["image", "video"])
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=12)
    save = subcommands.add_parser("download", help="Download one selected asset")
    save.add_argument("kind", choices=["image", "video"])
    save.add_argument("id", type=int)
    save.add_argument("--dir", required=True, help="Episode folder inside YouTube")
    save.add_argument("--quality", help="Video: medium or large. Image: large or fullhd")
    args = parser.parse_args()
    try:
        if args.command == "search":
            if not 1 <= args.limit <= 30 or not 1 <= len(args.query) <= 100:
                raise RuntimeError("Search needs a query of 1-100 characters and a limit of 1-30")
            data = api_get(args.kind, q=args.query, per_page=max(3, args.limit), safesearch="true")
            output = [summary(hit, args.kind) for hit in data.get("hits", [])[:args.limit]]
        else:
            quality = args.quality or ("medium" if args.kind == "video" else "large")
            valid = {"medium", "large"} if args.kind == "video" else {"large", "fullhd"}
            if quality not in valid:
                raise RuntimeError("Unsupported quality for this media type")
            output = download(args.kind, args.id, quality, args.dir)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except RuntimeError as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
