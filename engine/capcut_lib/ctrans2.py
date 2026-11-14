"""Переходи 21-40 (індекси 20..39). Параметри з пакетів Lumi, 3D-сцени за еталоном."""
import os, math
import numpy as np
from scipy import ndimage as ndi
from PIL import Image
from ctrans import *  # noqa
import ctrans as C

def smooth(e0, e1, x):
    x = np.clip((x - e0) / max(e1 - e0, 1e-6), 0, 1)
    return x * x * (3 - 2 * x)

def ramp(t, t0, t1):
    return float(np.clip((t - t0) / max(t1 - t0, 1e-6), 0, 1))

def ease(u):
    u = float(np.clip(u, 0, 1)); return u * u * (3 - 2 * u)

_noise_cache = {}
def fnoise(seed=0, scale=0.012, octaves=4):
    key = (seed, scale, octaves)
    if key not in _noise_cache:
        rng = np.random.default_rng(seed)
        acc = np.zeros((H, W), np.float32); amp = 1.0; tot = 0
        for o in range(octaves):
            s = scale * (2 ** o)
            gh, gw = max(2, int(H * s) + 2), max(2, int(W * s) + 2)
            g = rng.random((gh, gw)).astype(np.float32)
            up = ndi.zoom(g, (H / (gh - 1), W / (gw - 1)), order=3)[:H, :W]
            acc += up * amp; tot += amp; amp *= 0.5
        acc /= tot
        acc = (acc - acc.min()) / (acc.max() - acc.min())
        _noise_cache[key] = acc
    return _noise_cache[key]

def warp_noise(img, amount_px, phase=0.0, seed=3, scale=0.01):
    if amount_px < 0.3: return img
    nx = fnoise(seed, scale); ny = fnoise(seed + 7, scale)
    yy, xx = grid()
    ox = (np.roll(nx, int(phase * 40), 1) - 0.5) * 2 * amount_px
    oy = (np.roll(ny, int(phase * 40), 0) - 0.5) * 2 * amount_px
    return sample(img, yy + oy, xx + ox)

def luma(img): return img @ np.array([0.299, 0.587, 0.114], np.float32)

def tritone(img, mid, dark=(0, 0, 0), light=(1, 1, 1)):
    l = luma(img)[..., None]
    mid = np.array(mid[:3], np.float32); d = np.array(dark, np.float32); li = np.array(light, np.float32)
    lo = d + (mid - d) * np.clip(l * 2, 0, 1)
    hi = mid + (li - mid) * np.clip(l * 2 - 1, 0, 1)
    return np.where(l < 0.5, lo, hi)

def cube_faces(front, side, theta, h, push=0.0, rx=0.0, axis='y', scale=1.0, bg=None):
    """Куб з гранями front і side; theta 0 -> front у кадрі, 90 -> side у кадрі."""
    out = np.zeros_like(front) if bg is None else bg.copy()
    th = math.radians(theta); c, s = math.cos(th), math.sin(th)
    faces = []
    if axis == 'y':
        faces.append((front, dict(ry=theta, rx=rx, tx=-h * s, tz=h - h * c + push)))
        faces.append((side, dict(ry=theta - 90, rx=rx, tx=h * c, tz=h - h * s + push)))
    else:
        faces.append((front, dict(rx=-theta, ty=-h * s, tz=h - h * c + push)))
        faces.append((side, dict(rx=90 - theta, ty=h * c, tz=h - h * s + push)))
    faces.sort(key=lambda f: -f[1]['tz'])
    for img, kw in faces:
        rgb, a = persp(img, scale=scale, **kw)
        out = over(out, rgb, a)
    return out

# ---------------------------------------------------------------- 21..40
def t20(P, A, B, t):  # Танец кубиков
    th = P.k('LumiCube_57', 'rotateY', t)
    br = P.k('LumiBrightness_278', 'brightnessIntensity', t)
    a = np.clip(desat(A, -P.k('LumiSaturation_278', 'saturationIntensity', t)) * (1 + br * 0.6), 0, 1)
    push = math.sin(math.radians(th) * 2) * W * 0.55
    return cube_faces(a, B, th, W / 2, push)

def t21(P, A, B, t):  # Утренние блики
    return C._light_xfade(P, A, B, t, 'light5.mp4', 'LumiLayer_335', 'LumiLayer_336', 'LumiLayer_374')

def t22(P, A, B, t):  # Пылевой вихрь
    n = fnoise(11, 0.01, 5)
    p = ease(ramp(t, 0.05, 1.0)) * 1.1
    alive = smooth(p - 0.08, p, n)
    dust_amt = np.clip((p - n) * 3, 0, 1)
    dust = warp_noise(A, 40 * p * W / 960, phase=t * 3, seed=5, scale=0.02)
    dust = dust * (0.35 + 0.65 * fnoise(21, 0.05, 3)[..., None]) * (1 - 0.6 * dust_amt)[..., None]
    out = A * alive[..., None] + dust * (1 - alive)[..., None]
    out = barrel(out, P.k('LumiOpticsCompensation_66', 'fov', t) / 93 * 0.25)
    if t > 0.85:
        q = ease(ramp(t, 0.85, 1.35))
        reveal = smooth(1 - q * 1.15, 1.08 - q * 1.15, 1 - n)
        out = over(out, B, reveal)
    g = P.k('LumiDeepGlow_98', 'exposure', t)
    return np.clip(out + blur(out, 30) * g * 0.6, 0, 1)

def _glitch(img, amt, t, seed=0):
    if amt < 0.01: return img
    rng = np.random.default_rng(int(t * 1000) + seed)
    out = img.copy()
    rows = rng.integers(0, H, 12); hs = rng.integers(4, 40, 12); shifts = rng.integers(-60, 60, 12)
    for r, hh, sh in zip(rows, hs, shifts):
        out[r:r + hh] = np.roll(out[r:r + hh], int(sh * amt), 1)
    out = chroma_shift(out, 8 * amt)
    return out

def t23(P, A, B, t):  # Городской глитч
    out = A if t < 0.5 else B
    gi = P.k('LumiGrain_262', 'grainIntensity', t)
    out = _glitch(out, gi, t)
    hx = P.k('LumiDisplacementMap_262', 'horizontalIntensity', t)
    out = affine(out, dx=hx * W * 0.5, mode='mirror')
    moire = P.k('LumiGlitchSignal_262', 'moireNoise', t)
    nz = vframe(res(P, 'resource/video/replacement.mp4'), t, 30)
    out = screen(out, nz * 0.6, moire * 0.5)
    out = glow(out, P.k('LumiGlow_262', 'glowIntensity', t) * 1.6, 0.4, 40)
    out = screen(out, vframe(res(P, 'resource/video/light1.mp4'), t, 30))
    rng = np.random.default_rng(int(t * 997))
    return np.clip(out + rng.standard_normal((H, W, 1)).astype(np.float32) * 0.08 * gi, 0, 1)

def _streak(img, amount, t, seed=0, vertical=False):
    """Імітація pixel sort: розмазування яскравих ділянок рядками."""
    if amount < 0.02: return img
    rng = np.random.default_rng(seed + int(t * 60))
    L = int(20 + 300 * amount)
    sm = hblur(img, L) if not vertical else np.swapaxes(hblur(np.swapaxes(img, 0, 1), L), 0, 1)
    rows = (rng.random(H // 6 + 1) < 0.25 + 0.6 * amount).repeat(6)[:H].astype(np.float32)
    m = rows[:, None] * smooth(0.25, 0.6, luma(img))
    return over(img, sm, np.clip(m * 1.4 * min(1, amount * 2), 0, 1))

def t24(P, A, B, t):  # Неоновые царапины
    oa = P.k('LumiLayer_55', 'opacity', t) / 100
    ob = P.k('LumiLayer_56', 'opacity', t) / 100
    if t < 0.56: out = A
    elif t < 0.64: out = over(B * ob, A, oa * 0.6)
    else: out = affine(B, scale=P.k('LumiLayer_56', 'scale', t)[0] / 100) * ob
    th = P.k('LumiPixelSort_65', 'threshold', t)
    if 0.4 <= t <= 0.84: out = _streak(out, 1 - th, t, 3)
    out = blur(out, P.k('LumiFastBilateralBlur_63', 'radius', t) * 0.4)
    if 0.2 <= t <= 0.96:
        neon = vframe(res(P, 'resource/video/93nihong.mp4'), t - 0.2, 30)
        out = screen(out, neon, P.k('LumiAnimSeqLoadAndCrop_69', 'opacity_1_1', t, 1.0))
    dx, dy = shake(t, P.k('LumiSShake_63', 'ampRatio', t) * 150, 12)
    return affine(out, dx=dx, dy=dy)

def t25(P, A, B, t):  # Волнистые воспоминания
    caus = vframe(res(P, 'resource/video/i2v-960-30fps-warm.mp4'), t, 30)
    vi = P.k('LumiDisplacementMap_103', 'verticalIntensity', t)
    disp = (luma(caus) - 0.5)
    yy, xx = grid()
    def wav(img): return sample(img, yy + disp * vi * H * 0.8, xx + disp * vi * W * 0.2)
    bf = P.k('LumiExtract_104', 'blackField', t) / 255
    lb = blur(luma(B)[..., None], 6)[..., 0]
    reveal = smooth(bf - 0.15, bf + 0.05, lb) if t > 0.267 else np.zeros((H, W), np.float32)
    if t > 1.2: reveal = np.maximum(reveal, ramp(t, 1.2, 1.4))
    out = over(wav(A), wav(B), reveal)
    op = P.k('LumiLayer_102', 'opacity', t) / 100
    out = screen(out, caus * 0.45, op)
    out = np.clip(out * (1 + P.k('LumiBrightness_101', 'brightnessIntensity', t) * 0.25), 0, 1)
    return glow(out, P.k('LumiDeepGlow_101', 'exposure', t) * 0.5, 0.7, 30)

def t26(P, A, B, t):  # Черно-белая вспышка
    src = A if t < 1.0 else B
    g = ramp(t, 0.05, 0.25) * (1 - ramp(t, 1.6, 1.95))
    out = desat(src, g)
    out = np.clip((out - 0.5) * (1 + 0.3 * g) + 0.5, 0, 1)
    if 0.72 <= t <= 1.28:
        py = P.k('Lumi3DShape_61', 'Position_y', t)  # -6 .. 5
        yy, xx = grid()
        d = (yy - H / 2 + (xx - W / 2) * 0.6) / H - (-py / 11.0) * 1.6
        band = np.exp(-(d / 0.18) ** 2) * 0.84
        out = over(out, np.ones_like(out), blur(band[..., None], 12)[..., 0])
    e = P.k('LumiDeepGlow_54', 'exposure', t)
    out = np.clip(out + blur(out, 40) * e * 0.8, 0, 1)
    dx, dy = shake(t, 10 * e, 8)
    return affine(out, dx=dx, dy=dy)

def t27(P, A, B, t):  # Складывающийся куб (3D-сцена: за еталоном)
    D = P_dur(P, 1.6)
    out = np.zeros_like(A)
    zoom = math.sin(math.pi * ramp(t, 0.1, D - 0.15)) * W * 0.9
    for k, (x0, x1) in enumerate(((0, W // 2), (W // 2, W))):
        lag = 0.12 * k
        th = 90 * ease(ramp(t, 0.2 + lag, 1.25 + lag))
        fa = np.zeros_like(A); fa[:, x0:x1] = A[:, x0:x1]
        fb = np.zeros_like(B); fb[:, x0:x1] = B[:, x0:x1]
        ma = np.zeros((H, W), np.float32); ma[:, x0:x1] = 1
        for img, kw in sorted([(np.dstack([fa, ma]), dict(rx=-th, ty=-H / 2 * math.sin(math.radians(th)), tz=H / 2 - H / 2 * math.cos(math.radians(th)) + zoom)),
                               (np.dstack([fb, ma]), dict(rx=90 - th, ty=H / 2 * math.cos(math.radians(th)), tz=H / 2 - H / 2 * math.sin(math.radians(th)) + zoom))],
                              key=lambda f: -f[1]['tz']):
            rgb, a = persp(img, rz=8 * math.sin(math.pi * ramp(t, 0.1, D)), **kw)
            out = over(out, rgb[..., :3], a * rgb[..., 3])
    return out

def P_dur(P, d):
    return getattr(P, 'dur', d) or d

def t28(P, A, B, t):  # RGB-глитч
    out = A if t < 0.5 else B
    e = P.k('LumiSoftGlow_93', 'exposure', t)
    k = e / 3.7
    yy, xx = grid()
    out = sample(out, yy, xx + np.sin(yy / 18 + t * 30) * 25 * k)
    out = chroma_shift(out, 30 * k, 10 * k)
    out = _glitch(out, k, t, 5)
    nz = vframe(res(P, 'resource/video/replacement.mp4'), t, 30)
    out = screen(out, nz * 0.5, k * 0.6)
    lt = vframe(res(P, 'resource/video/light.mp4'), t, 30)
    out = screen(out, lt, P.k('LumiLayer_124', 'opacity', t) / 100)
    return np.clip(out + blur(out, 25) * e * 0.25, 0, 1)

def t29(P, A, B, t):  # Разрезание и панорамирование
    out = A if t < 0.333 else B
    ln = P.k('LumiPixelSort_51', 'length', t)
    if ln > 0.01: out = _streak(out, ln, t, 9)
    sz = P.k('LumiTurbulenceDisplacement_48', 'size', t)
    if t >= 0.333 and sz > 0.001:
        out = warp_noise(out, sz * W * 1.2, phase=P.k('LumiTurbulenceDisplacement_48', 'evolution', t) / 90, seed=4, scale=0.02)
    return out

def t30(P, A, B, t):  # Радужное искажение
    out = A if t < 0.5 else B
    sz = P.k('LumiTurbulenceDisplacement_136', 'size', t)
    out = warp_noise(out, sz * W * 0.8, phase=P.k('LumiTurbulenceDisplacement_136', 'evolution', t) / 90, seed=8, scale=0.015)
    ox = P.k('LumiChromaticAberration_136', 'offsetX', t); oy = P.k('LumiChromaticAberration_136', 'offsetY', t)
    out = chroma_shift(out, ox * W * 0.03, oy * H * 0.03)
    out = hblur(out, P.k('LumiDirectionalBlurs_136', 'blurIntensity', t) * W / 1280 * 1.5)
    out = desat(out, -P.k('LumiSaturation_136', 'saturationIntensity', t))
    return np.clip(out, 0, 1)

def t31(P, A, B, t):  # Клубные прожектора
    if t < 0.433 or P.k('LumiLayer_81', 'opacity', t) < 100:
        p = P.k('LumiLayer_14', 'position', t); s = P.k('LumiLayer_14', 'scale', t)[0] / 100
        out = affine(A, scale=s, dy=(p[1] - 640) * H / 1280 * 1.5, mode='mirror')
    else:
        out = None
    if t >= 0.433:
        p = P.k('LumiLayer_81', 'position', t); s = P.k('LumiLayer_81', 'scale', t)[0] / 100
        b = affine(B, scale=s, dy=(p[1] - 640) * H / 1280 * 1.5, mode='mirror')
        o = P.k('LumiLayer_81', 'opacity', t) / 100
        out = b if out is None else over(out, b, o)
    out = blur(out, P.k('LumiGaussianBlur_113', 'blurIntensity', t) * 0.5)
    lt = vframe(res(P, 'resource/video/111.mp4'), t, 30)
    return screen(out, lt, P.k('LumiLayer_970', 'opacity', t, 100) / 100)

def t32(P, A, B, t):  # Размытие и трепет
    if t < 0.4: out = A
    elif t > 1.667: out = B
    else:
        m = 1 - vframe(res(P, 'resource/video/Fade.mp4'), P.k('LumiAnimSeqLoadAndCrop_1053', 'seqTime', t), 30).mean(2)
        out = over(A, B, m if t > 0.833 else np.zeros_like(m)) if t <= 0.833 else over(A, B, np.maximum(m, ramp(t, 0.833, 1.2)))
    out = barrel(out, P.k('LumiOpticsCompensation_1103', 'fov', t) / 88 * 0.4)
    k = P.k('LumiChromaticAberration_1083', 'offsetX', t)
    out = chroma_shift(out, k * 25, k * 25)
    out = blur(out, P.k('LumiGaussianBlur_1056', 'blurIntensity', t) * W / 1080 * 0.15)
    ta = P.k('LumiTritone_1102', 'oriAlpha', t)
    out = over(tritone(out, (0.85, 0.75, 0.95), (0.05, 0.05, 0.1)), out, ta)
    dx, dy = shake(t, P.k('LumiSShake_1101', 'ampRatio', t) * 40, 10)
    return affine(out, dx=dx, dy=dy, mode='mirror')

def t33(P, A, B, t):  # Радужный фильтр
    if t < 0.5:
        out = A
        for n in ('LumiLayer_137', 'LumiLayer_138'):
            e = affine(A, scale=P.k(n, 'scale', t)[0] / 100)
            out = over(out, e, (1 - P.k(n, 'opacity', t) / 100) * 0.0 + 0.5 * ramp(t, 0.0, 0.2))
    else:
        out = B
        for n in ('LumiLayer_139', 'LumiLayer_140'):
            e = affine(B, scale=P.k(n, 'scale', t)[0] / 100)
            out = over(out, e, (1 - P.k(n, 'opacity', t) / 100) * 0.0 + 0.5 * (1 - ramp(t, 0.767, 1.0)))
    sz = P.k('LumiTurbulenceDisplacement_136', 'size', t)
    out = warp_noise(out, sz * W * 0.6, phase=P.k('LumiTurbulenceDisplacement_136', 'evolution', t) / 90, seed=2, scale=0.015)
    mid = P.k('LumiTritone_136', 'middleColor', t)
    ta = P.k('LumiTritone_136', 'oriAlpha', t)
    return over(tritone(out, mid, (0.02, 0.0, 0.1)), out, ta)

def t34(P, A, B, t):  # Вертикальный вырез 2
    rgb, a = seqframe(os.path.join(P.root, 'resource/seq/02'), t, 30)
    return over(A, B, a)

def t35(P, A, B, t):  # Милая замена
    out = np.zeros_like(A)
    if t < 0.633:
        p = P.k('LumiMotionBlur3D_42', 'position', t); s = P.k('LumiMotionBlur3D_42', 'scale_x', t)
        ry = P.k('LumiMotionBlur3D_42', 'rotation_y', t)
        rgb, a = persp(A, ry=ry, tx=(p[0] - 0.5) * W * 0.55, ty=(p[1] - 0.5) * H * 0.55, scale=s)
        out = over(out, rgb, a)
    if t >= 0.5:
        p = P.k('LumiMotionBlur3D_59', 'position', t); s = P.k('LumiMotionBlur3D_59', 'scale_x', t)
        ry = P.k('LumiMotionBlur3D_59', 'rotation_y', t)
        rgb, a = persp(B, ry=ry, tx=(p[0] - 0.5) * W * 0.55, ty=(p[1] - 0.5) * H * 0.55, scale=s)
        out = over(out, rgb, a)
    return out

def t36(P, A, B, t):  # Вложенная коробка (3D-сцена: за еталоном)
    D = 1.6
    u = ramp(t, 0.15, D - 0.2)
    th = 180 * ease(u)
    sc = 1 - 0.42 * math.sin(math.pi * u)
    h = W / 2 * sc
    out = np.zeros_like(A)
    c, s = math.cos(math.radians(th)), math.sin(math.radians(th))
    tilt = 20 * math.sin(math.pi * u)
    faces = [(A, dict(ry=th, tx=-h * s, tz=h - h * c)),
             (B, dict(ry=th - 180, tx=h * s, tz=h + h * c)),
             (desat(A, 0.4) * 0.8, dict(ry=th - 90, tx=h * c, tz=h - h * s)),
             (desat(B, 0.4) * 0.8, dict(ry=th + 90, tx=-h * c, tz=h + h * s))]
    push = W * 0.7 * math.sin(math.pi * u)
    for img, kw in sorted(faces, key=lambda f: -f[1]['tz']):
        kw = dict(kw); kw['tz'] += push
        rgb, a = persp(img, rx=tilt, scale=sc, **kw)
        out = over(out, rgb, a)
    return out

def t37(P, A, B, t):  # Яркое стирание
    return C._light_xfade(P, A, B, t, 'lightX.mp4', 'LumiLayer_354', 'LumiLayer_355', 'LumiLayer_370')

def t38(P, A, B, t):  # Дверь-портал (3D-сцена: за еталоном)
    D = 1.6
    yy, xx = grid()
    # коридор: стіни з A, у глибині B, що наближається
    d = ease(ramp(t, 0.25, D - 0.1))
    sback = 0.3 + 0.7 * d
    u = (xx - W / 2) / (W / 2); v = (yy - H / 2) / (H / 2)
    r = np.maximum(np.abs(u), np.abs(v))
    inside = r <= sback
    q = np.clip((1 / np.maximum(r, 1e-3) - 1) / (1 / sback - 1 + 1e-6), 0, 1)
    side = np.abs(u) >= np.abs(v)
    wu = np.where(side, np.sign(u) * (1 - q * 0.5), u / np.maximum(r, 1e-3))
    wv = np.where(side, v / np.maximum(r, 1e-3), np.sign(v) * (1 - q * 0.5))
    wall = sample(A * 0.7, (wv + 1) * H / 2, (wu + 1) * W / 2, mode='mirror')
    back = sample(B, (v / sback + 1) * H / 2, (u / sback + 1) * W / 2, mode='nearest')
    out = np.where(inside[..., None], back, wall)
    out = out * (0.55 + 0.45 * (1 - (1 - q) * (1 - inside)))[..., None]
    # двері: дві половини A розходяться
    o = ease(ramp(t, 0.0, 0.45))
    if o < 1:
        for sgn, (x0, x1) in ((-1, (0, W // 2)), (1, (W // 2, W))):
            half = np.zeros_like(A); half[:, x0:x1] = A[:, x0:x1]
            m = np.zeros((H, W), np.float32); m[:, x0:x1] = 1
            rgb, a = persp(np.dstack([half, m]), ry=sgn * 80 * o, tx=sgn * (W / 4) * (1 - math.cos(math.radians(80 * o))) * 2,
                           tz=(W / 4) * math.sin(math.radians(80 * o)) * 2)
            out = over(out, rgb[..., :3], a * rgb[..., 3])
    return out

def t39(P, A, B, t):  # Прожектор (картка на нитці)
    bg = blur(A, P.k('LumiGaussianBlur_223', 'blurIntensity', t) * 0.35) * (0.4 + 0.6 * P.k('LumiLayer_223', 'opacity', t) / 100)
    if t >= 0.967:
        return blur(affine(B, scale=P.k('LumiLayer_232', 'scale', t)[0] / 100), P.k('LumiRadialBlur_233', 'amount', t) * 0.1)
    rot = P.k('LumiLayer_225', 'p1_rotation', t)
    s = P.k('LumiLayer_225', 'scale', t)[0] / 100 if t >= 0.667 else 0.6
    cw, ch = W * 0.24, H * 0.62
    card = np.ones((H, W, 3), np.float32) * 0.96
    inner = affine(B, scale=(0.21, 0.5))
    m_in = round_mask(0.21, 0.5, 2)
    card = over(card, inner, m_in)
    m = round_mask(0.24, 0.62, 4)
    pivot_y = H / 2 - ch / 2 - H * 0.12
    # нитка
    yy, xx = grid()
    string = (np.abs(xx - W / 2) < 1.2) & (yy > H / 2 - ch / 2 - H * 0.12) & (yy < H / 2 - ch / 2)
    m = np.maximum(m, string.astype(np.float32))
    card = np.where(string[..., None], 0.85, card)
    rgb, a = affine(np.dstack([card, m]), scale=s * 1.6, rot=rot, cx=W / 2, cy=pivot_y, dy=-(H / 2 - pivot_y) * (s * 1.6 - 1) * 0.0, alpha=True)
    out = over(bg, rgb, a * ramp(t, 0.03, 0.15))
    if t >= 0.667:
        out = zoom_blur(out, P.k('LumiRadialBlur_233', 'amount', t), n=8)
    return out

FUNCS = [t20, t21, t22, t23, t24, t25, t26, t27, t28, t29, t30, t31, t32, t33, t34, t35, t36, t37, t38, t39]
