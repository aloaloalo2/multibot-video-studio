#!/usr/bin/env python3
"""The studio's music library from the YouTube Audio Library (backend/music_library.py).

  python3 tools/music_library.py import FOLDER PICK.json   copies the downloaded «Title - Artist.mp3» files of PICK
                                                          into the library, measured once
  python3 tools/music_library.py vocals [--all]           finds tracks with singing or speech and takes them out of the
                                                          library: a background under the narration has no voice of
                                                          its own (local Whisper, free)
  python3 tools/music_library.py list                     the library, a line a track
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import music_library  # noqa: E402
import store  # noqa: E402

WHISPER = "mlx-community/whisper-small-mlx"


def words_in(path: Path, seconds: float) -> int:
    """Words Whisper hears with confidence in three 20-second windows of the track (a quarter, half, three quarters)."""
    import mlx_whisper
    heard = 0
    with tempfile.TemporaryDirectory() as tmp:
        for share in (.25, .5, .75):
            clip = Path(tmp) / f"w{share}.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, seconds * share - 10):.2f}", "-t", "20", "-i", str(path),
                            "-ac", "1", "-ar", "16000", str(clip)], check=True)
            result = mlx_whisper.transcribe(str(clip), path_or_hf_repo=WHISPER, verbose=None, condition_on_previous_text=False,
                                            temperature=0.0)   # no retries at higher temperatures: a loop on music is its own answer
            for segment in result.get("segments", []):
                # Whisper invents text on instrumental music: a loop of one word (compression far over 2.4), a
                # log-probability it cannot compute, or letters of another script; those are not a voice
                logprob = float(segment.get("avg_logprob", -9))
                if (segment.get("no_speech_prob", 1) < .5 and math.isfinite(logprob) and logprob > -.8
                        and float(segment.get("compression_ratio", 9)) <= 2.4):
                    heard += len(re.findall(r"[A-Za-zÀ-ÿ']{2,}", str(segment.get("text", ""))))
    return heard


def main(argv: list[str]) -> int:
    if argv[:1] == ["import"] and len(argv) == 3:
        pick = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        print(json.dumps(music_library.import_folder(Path(argv[1]).expanduser(), pick), ensure_ascii=False))
        return 0
    if argv[:1] == ["vocals"]:
        for row in music_library.catalog():
            if "vocals" in row and "--all" not in argv:
                continue
            count = words_in(music_library.root() / row["file"], float(row.get("seconds") or 120))
            music_library.mark_vocals(row["id"], count >= 6)
            print(f"{'ГОЛОС' if count >= 6 else 'ok   '} {count:>3} слів  {row['title']} — {row['artist']}", flush=True)
        gone = music_library.remove_vocal_tracks()
        print(f"прибрано з голосом: {len(gone)}", flush=True)
        return 0
    if argv[:1] == ["list"]:
        for row in music_library.public():
            print(f"{row['category']:<14} {row['title']} — {row['artist']}{'  [голос]' if row.get('vocals') else ''}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
