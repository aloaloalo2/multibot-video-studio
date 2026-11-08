"""audio/mix.py — build the soundtrack (voice + music + SFX + ambience), duck, master, and mux.

  python audio/mix.py --project projects/my-video [--video build/video_silent.mp4] [--no-music] [--no-sfx]

Reads config.json and story/shots.json:
  shot "sfx":  [{"at": 0.2, "name": "whoosh", "gain": -8, "dur": 0.7, "seed": 3, "pitch": 1.0}]  (at = seconds from shot start;
               name may also be a path to your own .wav/.mp3 relative to the project)
  shot "amb":  {"name": "rain", "gain": -20}   ambience bed looped under that shot (0.4 s fades)
  story "sfx":  [{"t": 81.4, "name": "ding", "gain": -10, "seed": 3}]  the same cues at an absolute time t of the film
               (seconds from its start): they stay put when the shots are cut again
  story "music": plan for audio/music.py  (or config.music.file = your own track, looped/trimmed)
Ducking: music −9 dB and ambience −5 dB while the narrator speaks. Master: loudness-normalised to config.loudness (default −14 LUFS).
Outputs build/mix.wav and, if the silent video exists, out/<title>.mp4.
"""
import argparse, json, os, re, subprocess, sys, tempfile
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from dsp import SR, BLOCK, secs, db, rms_db, place, write_wav, as_stereo, minus_lp
import sfx as SFX
import music as MUSIC


def envelope(x, att=0.03, rel=0.45):
    """smoothed voice level 0..1 used to duck the music. The level of each 10 ms is read block by block (BLOCK is a
    whole number of them), so a whole film's voice gets no float copies of itself."""
    hop = secs(0.01)
    assert BLOCK % hop == 0
    mono = lambda y: np.abs(y).mean(axis=1) if y.ndim == 2 else np.abs(y)
    frames = np.concatenate([np.add.reduceat(mono(x[i:i + BLOCK]) ** 2, np.arange(0, len(x[i:i + BLOCK]), hop))
                             for i in range(0, len(x), BLOCK)])
    frames = np.sqrt(frames / hop)
    lv = np.clip((20 * np.log10(frames + 1e-9) + 50) / 30, 0, 1)
    out = np.zeros_like(lv); a, r = np.exp(-0.01 / att), np.exp(-0.01 / rel); v = 0.0
    for i, s in enumerate(lv):
        v = a * v + (1 - a) * s if s > v else r * v + (1 - r) * s; out[i] = v
    return np.repeat(out, hop)[: len(x)]


def load_any(path, sr=SR):
    """Decode any audio/video file with ffmpeg into stereo float32 [n, 2], read straight into one array (the pipe's bytes
    and a copy of them would hold a whole film's voice three times, tools/common.load_audio)."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    try: guess = float(probe.stdout.strip()) + 1
    except ValueError: guess = 60.0
    buf = np.empty(int(guess * sr) * 2, np.float32); got = 0
    with tempfile.TemporaryFile() as err:
        p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-acodec", "pcm_f32le", "-ac", "2", "-ar", str(sr), "-"],
                             stdout=subprocess.PIPE, stderr=err)
        while True:
            if got == buf.nbytes: buf = np.resize(buf, len(buf) + 60 * sr * 2)
            k = p.stdout.readinto(memoryview(buf).cast("B")[got:])
            if not k: break
            got += k
        p.stdout.close()
        if p.wait() != 0:
            err.seek(0); sys.exit(f"ffmpeg could not decode {path}: {err.read().decode(errors='replace')[-800:]}")
    return buf[: got // 8 * 2].reshape(-1, 2)


def fit(x, n):
    """x cut or padded with silence to n samples (a cut keeps the same array, no copy)."""
    return x[:n] if len(x) >= n else np.concatenate([x, np.zeros((n - len(x), 2), np.float32)])


def voice_level(voice):
    """The narrator's level (dB RMS of the spoken parts, read block by block) and the smoothed envelope the music and
    ambience duck under."""
    total, count = 0.0, 0
    for i in range(0, len(voice), BLOCK):
        part = voice[i:i + BLOCK]; loud = part[np.abs(part).mean(1) > db(-40)]
        total += float(np.square(loud, dtype=np.float64).sum()); count += loud.size
    return (20 * np.log10(np.sqrt(total / count) + 1e-12) if count else -20), envelope(voice)


def duck(x, env, depth):
    """x (stereo) lowered by `depth` dB while the narrator speaks, in place and block by block."""
    for i in range(0, len(x), BLOCK):
        x[i:i + BLOCK] *= db(depth * env[i:i + BLOCK])[:, None]
    return x


def add(dst, part, gain=1.0):
    """dst += part * gain in place, block by block (the product of a whole film would be one more copy of it)."""
    for i in range(0, len(dst), BLOCK):
        dst[i:i + BLOCK] += part[i:i + BLOCK] * gain
    return dst


def beds(P, cfg, story, n, v_rms, env, music=True, sfx=True):
    """The sound under the voice, a part at a time, as main() mixes it: (part, gain, at) for the ducked music (the whole
    film, at 0), then for SFX + ambience window by window; each part, a stereo float32 array, goes into the mix at
    sample `at` as part * gain (add). A part is made only after the caller has let the one before go, so a whole film
    holds no more than a couple of copies of itself in the RAM (render_bed in the Studio's razgon_bridge.py takes the
    same parts for its timeline's music-and-effects clip)."""
    total = story.get("duration") or story["shots"][-1]["end"]
    # ---- music
    mcfg = cfg.get("music", {}) or {}
    if mcfg.get("enabled", True) and music:
        if mcfg.get("file"):
            mus = load_any(os.path.join(P, mcfg["file"]))
            reps = int(np.ceil(n / len(mus))); mus = np.concatenate([mus] * reps)[:n]
            k = secs(3); mus[-k:] *= np.linspace(1, 0, k)[:, None]
        else:
            path = os.path.join(P, "build", "music.wav")
            plan = story.get("music") or MUSIC.default_plan(total)
            print(f"generating music: {len(plan)} section(s) — " + ", ".join(f"{s['mood']}@{s.get('intensity', .5)}" for s in plan))
            mus = MUSIC.render_score(plan, total, mcfg.get("seed", 1), mcfg.get("key")); write_wav(path, mus)
        mus = as_stereo(mus)[:n]
        if len(mus) < n: mus = np.concatenate([mus, np.zeros((n - len(mus), 2), np.float32)])
        mus *= db(v_rms + mcfg.get("gainDb", -17) - rms_db(mus))
        yield duck(mus, env, -9), 1.0, 0
        del mus
    # ---- sfx + ambience, made one window of BLOCK samples at a time: the same additions in the same order as into
    # whole-film arrays, without two whole-film arrays
    scfg = cfg.get("sfx", {}) or {}
    if scfg.get("enabled", True) and sfx:
        cues = []
        for s in story["shots"]:
            for c in s.get("sfx", []) or []: cues.append({**c, "t": s["start"] + float(c.get("at", 0))})
        for c in story.get("sfx", []) or []: cues.append({**c, "t": float(c["t"])})
        beds_of = [s for s in story["shots"] if s.get("amb")]
        gain = db(scfg.get("gainDb", -6) + (v_rms + 18))   # SFX levels are relative to the voice level
        bases, loops, sounds, done = {}, {}, {}, set()
        for w0 in range(0, n, BLOCK):
            w1 = min(n, w0 + BLOCK)
            bed = np.zeros((w1 - w0, 2), np.float32); hits = np.zeros((w1 - w0, 2), np.float32)
            for k, s in enumerate(beds_of):
                at = secs(s["start"])
                if at >= w1 or at + secs(s["end"] - s["start"]) <= w0: continue
                if k not in loops:
                    am = s["amb"]; ln = s["end"] - s["start"]
                    key = (am["name"], am.get("seed", 1)); base = bases.get(key)
                    if base is None: base = bases[key] = SFX.make(am["name"], dur=6.0, seed=am.get("seed", 1))
                    loop = np.concatenate([base] * int(np.ceil(ln / (len(base) / SR) + 1)))[: secs(ln)]
                    f = min(secs(0.4), len(loop) // 2); loop[:f] *= np.linspace(0, 1, f)[:, None]; loop[-f:] *= np.linspace(1, 0, f)[:, None]
                    loops[k] = loop
                place(bed, loops[k], at - w0, db(s["amb"].get("gain", -20)))
            for k, c in enumerate(cues):
                at = secs(c["t"])
                if at >= w1 or k in done: continue
                if k not in sounds:
                    nm = c["name"]
                    if re.search(r"\.(wav|mp3|ogg|flac|m4a)$", nm, re.I): sounds[k] = load_any(os.path.join(P, nm))
                    else: sounds[k] = SFX.make(nm, dur=c.get("dur"), seed=c.get("seed"), pitch=c.get("pitch"))
                place(hits, sounds[k], at - w0, db(c.get("gain", -8)))
            # a loop or a sound that ends before the next window is not needed again
            for k in [k for k, x in loops.items() if secs(beds_of[k]["start"]) + len(x) <= w1]: del loops[k]
            for k in [k for k, x in sounds.items() if secs(cues[k]["t"]) + len(x) <= w1]: del sounds[k]; done.add(k)
            hits += duck(bed, env[w0:w1], -5)
            yield hits, gain, w0
        print(f"sfx: {len(cues)} cue(s), ambience on {len(beds_of)} shot(s)")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--project", required=True); ap.add_argument("--video"); ap.add_argument("--no-music", action="store_true"); ap.add_argument("--no-sfx", action="store_true"); ap.add_argument("--out")
    a = ap.parse_args(); P = a.project
    with open(os.path.join(P, "config.json"), encoding="utf-8") as config_file:
        cfg = json.load(config_file)
    with open(os.path.join(P, "story", "shots.json"), encoding="utf-8") as story_file:
        story = json.load(story_file)
    total = story.get("duration") or story["shots"][-1]["end"]; n = secs(total)
    voice = fit(load_any(os.path.join(P, cfg["voiceover"])), n)
    v_rms, env = voice_level(voice)
    mix = voice; del voice   # the voice is not needed again: the mix is built on it in place
    for part, gain, at in beds(P, cfg, story, n, v_rms, env, not a.no_music, not a.no_sfx):
        add(mix[at:at + len(part)], part, gain); del part
    del env
    # ---- master: gentle high-pass, soft clip, loudness normalise with ffmpeg
    minus_lp(mix, 25)
    peak = np.float32(max(float(np.abs(mix[i:i + BLOCK]).max(initial=0)) for i in range(0, len(mix), BLOCK)))
    if peak > 0.95: mix = np.tanh(mix / peak * 1.2) / np.tanh(1.2) * 0.95
    raw = os.path.join(P, "build", "mix_raw.wav"); write_wav(raw, mix)
    out_wav = os.path.join(P, "build", "mix.wav"); lufs = cfg.get("loudness", -14)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11", "-ar", str(SR), out_wav], check=True)
    print(f"wrote {out_wav}  ({total:.1f}s, target {lufs} LUFS)")
    video = a.video or os.path.join(P, "build", "video_silent.mp4")
    if os.path.exists(video):
        safe = re.sub(r"[^\w\- ]+", "", cfg.get("title") or "video").strip().replace(" ", "_") or "video"
        out = a.out or os.path.join(P, "out", f"{safe}.mp4"); os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video, "-i", out_wav, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)
        print(f"FINAL VIDEO: {out}")
    else:
        print(f"(no silent video at {video} yet — render it, then run this again to mux)")


if __name__ == "__main__":
    main()
