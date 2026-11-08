"""Fifteen short stereo transition designs, synthesized locally at 48 kHz."""
from functools import partial

import numpy as np
from dsp import SR, secs, noise, lp, hp, bp, sine, expdec, normalize

DURATIONS = dict(air=.65, silk=.8, whip=.32, camera=.35, snap=.22, sweep=.6, down=.65,
                 rise=.9, reverse=.65, bass=.5, glitch=.4, pixel=.45, neon=.6, warp=.7, shimmer=.8)


def render(style, dur=None, seed=7, **_):
    dur = DURATIONS[style] if dur is None else max(.1, min(6., float(dur)))
    n = secs(dur)
    t = np.arange(n) / SR
    u = np.linspace(0, 1, n)
    white = noise(n, seed)
    soft = lp(white, 1800)
    air = bp(white, 1500, 9500)
    hump = np.sin(np.pi * u) ** 2
    if style == 'air':
        x = air * hump + .15 * sine(1700 + 2200 * u, n) * hump
    elif style == 'silk':
        x = lp(white, 800) * np.sin(np.pi * u) ** 3 + .1 * air * hump
    elif style == 'whip':
        x = hp(white, 3500) * np.exp(-((u - .55) / .13) ** 2) + .18 * sine(700 * 6 ** u, n) * hump
    elif style == 'camera':
        x = hp(white, 2600) * (np.exp(-t / .006) + .7 * np.exp(-np.maximum(t - .075, 0) / .013) * (t >= .075))
        x += .12 * sine(850, n) * np.exp(-t / .04)
    elif style == 'snap':
        x = .5 * air * expdec(n, .008) + .6 * sine(140 - 80 * u, n) * expdec(n, .035)
    elif style == 'sweep':
        x = air * u ** 1.2 * (1 - u) ** .4 + .25 * sine(350 * 9 ** u, n) * hump
    elif style == 'down':
        x = soft * hump + .35 * sine(2200 * .06 ** u, n) * hump
    elif style == 'rise':
        x = .5 * white * u ** 3 + .25 * sine(100 * 12 ** u, n) * u ** 2
    elif style == 'reverse':
        x = bp(white, 700, 5000) * np.exp(-(1 - u) * 8) + .3 * sine(90 + 300 * u, n) * u ** 4
    elif style == 'bass':
        x = sine(140 * .28 ** u, n) * expdec(n, .12) + .22 * air * expdec(n, .035)
    elif style == 'glitch':
        gate = ((np.floor(u * 19) % 4) < 2).astype(float)
        x = (np.sign(sine(400 + 1200 * np.floor(u * 6) / 6, n)) * .2 + .2 * air) * gate * hump
    elif style == 'pixel':
        steps = np.minimum((u * 5).astype(int), 4)
        notes = np.array([660, 880, 1320, 1760, 1320])
        pulse = np.exp(-((u * 5) % 1) * 5)
        x = sine(notes[steps], n) * pulse * (1 - u) + .07 * air * hump
    elif style == 'neon':
        x = sine(650 + 1000 * np.sin(np.pi * u) + 90 * sine(30, n), n) * hump * .6 + air * hump * .25
    elif style == 'warp':
        x = sine(180 + 1500 / (1 + np.exp(10 * (u - .45))), n) * hump * .4 + soft * hump
    else:  # shimmer
        x = sum(sine(f, n) * np.exp(-np.maximum(t - onset, 0) / .12) * (t >= onset)
                for f, onset in [(1800, 0), (2700, .07), (3600, .13), (4500, .2)]) * .22 + .08 * air * hump
    # Quiet edges and a changing stereo position, with no DC offset or clipped samples.
    edge = min(secs(.008), n // 4)
    x[:edge] *= np.linspace(0, 1, edge)
    x[-edge:] *= np.linspace(1, 0, edge)
    x -= x.mean()
    pan = np.linspace(.2, .8, n) if style in {'air', 'whip', 'sweep', 'down', 'warp'} else np.full(n, .5)
    stereo = np.stack([x * np.cos(pan * np.pi / 2), x * np.sin(pan * np.pi / 2)], axis=1).astype(np.float32)
    return normalize(stereo, -3)


LIB = {'tr_' + key: {'fn': partial(render, key), 'dur': duration, 'desc': 'Transition: ' + key}
       for key, duration in DURATIONS.items()}
