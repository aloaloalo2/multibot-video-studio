"""Відтворення 20 трендових переходів CapCut на numpy.

Параметри (тривалість, ключові кадри, криві, ресурси) беруться з розпакованих
пакетів Lumi. Кожна функція tNN(ctx, t) повертає кадр float32 HxWx3 у 0..1.
"""
import os, glob, math, subprocess, functools
import numpy as np
from scipy import ndimage as ndi
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
import sys; sys.path.insert(0, HERE)
from lumi_parse import load

W, H = int(os.environ.get("CAPCUT_W", 960)), int(os.environ.get("CAPCUT_H", 540))
FPS = 30

# ---------------------------------------------------------------- keyframes
def _bez1(p1, p2, u):
    return 3 * (1 - u) ** 2 * u * p1 + 3 * (1 - u) * u * u * p2 + u ** 3

def bezier_ease(x1, y1, x2, y2, x):
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(40):
        m = (lo + hi) / 2
        if _bez1(x1, x2, m) < x: lo = m
        else: hi = m
    return _bez1(y1, y2, (lo + hi) / 2)

class Track:
    def __init__(self, segs):
        self.segs = [s for s in segs if s[1][1] > s[1][0]] or segs[:1]
    def __call__(self, t):
        segs = self.segs
        def val(v): return np.array(v, float) if len(v) > 1 else float(v[0])
        if t <= segs[0][1][0]: return val(segs[0][2][0])
        if t >= segs[-1][1][1]: return val(segs[-1][2][1])
        for s in segs:
            t0, t1 = s[1]
            if t0 <= t <= t1:
                e = s[0]
                if len(e) >= 12: x1, y1, x2, y2 = e[0], e[3], e[6], e[9]
                else: x1, y1, x2, y2 = e[:4]
                u = bezier_ease(x1, y1, x2, y2, (t - t0) / (t1 - t0))
                vs = s[2]
                if len(vs) == 4:  # просторова крива: p0, p1, вихідна, вхідна
                    p0, p1, c1, c2 = (np.array(v, float) for v in vs)
                    return (1 - u) ** 3 * p0 + 3 * (1 - u) ** 2 * u * c1 + 3 * (1 - u) * u * u * c2 + u ** 3 * p1
                v0, v1 = val(vs[0]), val(vs[1])
                return v0 + (v1 - v0) * u
        # проміжок між сегментами: тримаємо кінцеве значення попереднього
        prev = [s for s in segs if s[1][1] <= t][-1]
        return val(prev[2][1])

class Pkg:
    def __init__(self, path):
        self.d = load(path)
        self.root = self.d['root']
        self.dur = float(self.d['ae_compDurations'][1])
        kf = self.d.get('ae_keyframes') or {}
        self.tracks = {}
        for k, segs in kf.items():
            node, prop, _ = k.split('#')
            self.tracks[(node, prop)] = Track(segs)
    def k(self, node_prefix, prop, t, default=0.0):
        for (n, p), tr in self.tracks.items():
            if p == prop and (n == node_prefix or n.startswith(node_prefix)):
                return tr(t)
        a = self.attr(node_prefix)
        return a.get(prop, default) if a else default
    def attr(self, node_prefix):
        for n, a in self.d['ae_attribute'].items():
            if n == node_prefix or n.startswith(node_prefix):
                return a
        return {}

# ---------------------------------------------------------------- image ops
def fit_cover(img, w=W, h=H):
    iw, ih = img.size
    s = max(w / iw, h / ih)
    img = img.resize((max(w, round(iw * s)), max(h, round(ih * s))), Image.LANCZOS)
    x = (img.width - w) // 2; y = (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))

def to_f(img):
    return np.asarray(img.convert('RGB'), np.float32) / 255.0

def load_rgba(path, w=W, h=H):
    im = fit_cover(Image.open(path).convert('RGBA'), w, h)
    a = np.asarray(im, np.float32) / 255.0
    return a[..., :3], a[..., 3]

_grid = None
def grid():
    global _grid
    if _grid is None:
        _grid = np.mgrid[0:H, 0:W].astype(np.float32)
    return _grid

def sample(img, ys, xs, mode='reflect', cval=0.0):
    out = np.empty(ys.shape + (img.shape[2],), np.float32)
    for c in range(img.shape[2]):
        out[..., c] = ndi.map_coordinates(img[..., c], [ys, xs], order=1, mode=mode, cval=cval)
    return out

def affine(img, scale=1.0, rot=0.0, dx=0.0, dy=0.0, cx=None, cy=None, mode='reflect', alpha=False):
    """Масштаб/поворот навколо (cx,cy), потім зсув (dx,dy) у пікселях."""
    if np.isscalar(scale): sx = sy = scale
    else: sx, sy = scale
    cx = W / 2 if cx is None else cx; cy = H / 2 if cy is None else cy
    yy, xx = grid()
    x = xx - cx - dx; y = yy - cy - dy
    r = math.radians(rot); c, s = math.cos(r), math.sin(r)
    xs = (c * x + s * y) / max(sx, 1e-6) + cx
    ys = (-s * x + c * y) / max(sy, 1e-6) + cy
    if alpha:
        rgba = np.dstack([img, np.ones(img.shape[:2], np.float32)]) if img.shape[2] == 3 else img
        o = sample(rgba, ys, xs, mode='constant', cval=0.0)
        return o[..., :3], o[..., 3]
    return sample(img, ys, xs, mode=mode)

def over(base, top, a):
    a = np.clip(a, 0, 1)[..., None] if np.ndim(a) == 2 else np.clip(a, 0, 1)
    return top * a + base * (1 - a)

def screen(a, b, o=1.0): return a + (1 - (1 - a) * (1 - b) - a) * o
def add(a, b, o=1.0): return np.clip(a + b * o, 0, 1)
def lighten(a, b, o=1.0): return a + (np.maximum(a, b) - a) * o

def blur(img, sigma_y, sigma_x=None):
    sigma_x = sigma_y if sigma_x is None else sigma_x
    if max(sigma_x, sigma_y) < 0.3: return img
    f = int(max(1, min(4, max(sigma_x, sigma_y) // 6)))
    if f > 1:
        small = img[::f, ::f]
        b = ndi.gaussian_filter(small, (sigma_y / f, sigma_x / f, 0), mode='reflect')
        return _up(b, img.shape).astype(np.float32)
    return ndi.gaussian_filter(img, (sigma_y, sigma_x, 0), mode='reflect')

def _up(b, shape):
    zy = shape[0] / b.shape[0]; zx = shape[1] / b.shape[1]
    o = ndi.zoom(b, (zy, zx, 1), order=1)
    return o[:shape[0], :shape[1]]

def hblur(img, length):
    n = int(length)
    if n < 2: return img
    return ndi.uniform_filter1d(img, n, axis=1, mode='reflect')

def zoom_blur(img, amount, cx=0.5, cy=0.5, n=10, spin=False):
    """Радіальне розмиття: amount 0..100 як у AE."""
    if amount < 0.5: return img
    acc = np.zeros_like(img)
    for i in range(n):
        f = i / (n - 1)
        if spin:
            acc += affine(img, rot=(f - 0.5) * amount * 0.4, cx=cx * W, cy=cy * H)
        else:
            acc += affine(img, scale=1 + f * amount * 0.004, cx=cx * W, cy=cy * H)
    return acc / n

def exposure(img, stops, gamma=1.0):
    o = np.clip(img * (2.0 ** stops), 0, 1)
    if gamma != 1.0: o = o ** (1.0 / gamma)
    return o

def glow(img, intensity, threshold=0.6, radius=40):
    if intensity <= 0.001: return img
    lum = img.mean(2, keepdims=True)
    hi = img * np.clip((lum - threshold) / (1 - threshold + 1e-6), 0, 1)
    return np.clip(img + blur(hi, radius) * intensity * 2.5, 0, 1)

def desat(img, amount):
    g = img.mean(2, keepdims=True)
    return img + (g - img) * amount

def vignette(img, amount, mid=0.7, feather=0.8):
    if amount <= 0.001: return img
    yy, xx = grid()
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
    m = np.clip((r - mid * (1 - feather)) / max(feather, 1e-3), 0, 1) ** 2
    return img * (1 - amount * m)[..., None]

def barrel(img, k, mode='reflect'):
    """k>0 — опуклість (лінза), k<0 — втягування."""
    if abs(k) < 1e-3: return img
    yy, xx = grid()
    x = (xx - W / 2) / (W / 2); y = (yy - H / 2) / (W / 2)
    r2 = x * x + y * y
    f = 1 / (1 + k * r2)
    return sample(img, y * f * (W / 2) + H / 2, x * f * (W / 2) + W / 2, mode=mode)

def chroma_shift(img, dx_px, dy_px=0.0):
    if abs(dx_px) < 0.5 and abs(dy_px) < 0.5: return img
    o = img.copy()
    o[..., 0] = ndi.shift(img[..., 0], (dy_px, dx_px), order=1, mode='reflect')
    o[..., 2] = ndi.shift(img[..., 2], (-dy_px, -dx_px), order=1, mode='reflect')
    return o

def bokeh(img, radius):
    if radius < 1: return img
    f = 2
    small = img[::f, ::f] ** 3
    r = max(1, int(radius / f))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    k = ((xx * xx + yy * yy) <= r * r).astype(np.float32); k /= k.sum()
    from scipy.signal import fftconvolve
    b = np.stack([fftconvolve(small[..., c], k, mode='same') for c in range(3)], -1)
    b = np.clip(b, 0, None) ** (1 / 3)
    return np.clip(_up(b, img.shape), 0, 1)

def persp(img, rx=0, ry=0, rz=0, tx=0, ty=0, tz=0, scale=1.0, fov=39.6, alpha=True, src_w=None, src_h=None):
    """Площина з картинкою в 3D: повороти в градусах, зсуви в пікселях кадру."""
    f = (W / 2) / math.tan(math.radians(fov / 2))
    ax, ay, az = (math.radians(v) for v in (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(ax), -math.sin(ax)], [0, math.sin(ax), math.cos(ax)]])
    Ry = np.array([[math.cos(ay), 0, math.sin(ay)], [0, 1, 0], [-math.sin(ay), 0, math.cos(ay)]])
    Rz = np.array([[math.cos(az), -math.sin(az), 0], [math.sin(az), math.cos(az), 0], [0, 0, 1]])
    R = Rz @ Ry @ Rx * scale
    # точка площини (u,v,0) -> камера: R@(u,v,0) + (tx,ty,f+tz)
    Hm = np.array([[R[0, 0], R[0, 1], tx], [R[1, 0], R[1, 1], ty], [R[2, 0], R[2, 1], f + tz]])
    K = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1]])
    M = K @ Hm
    Mi = np.linalg.inv(M)
    yy, xx = grid()
    p = np.stack([xx.ravel(), yy.ravel(), np.ones(xx.size, np.float32)])
    q = Mi @ p
    u = (q[0] / q[2]).reshape(H, W) + W / 2
    v = (q[1] / q[2]).reshape(H, W) + H / 2
    behind = (q[2] < 0).reshape(H, W)
    rgba = np.dstack([img, np.ones(img.shape[:2], np.float32)])
    o = sample(rgba, v, u, mode='constant')
    o[behind] = 0
    return o[..., :-1], o[..., -1]

def round_mask(w_frac, h_frac, radius_px, cx=W / 2, cy=H / 2):
    yy, xx = grid()
    hw = W * w_frac / 2; hh = H * h_frac / 2
    dx = np.maximum(np.abs(xx - cx) - (hw - radius_px), 0)
    dy = np.maximum(np.abs(yy - cy) - (hh - radius_px), 0)
    d = np.sqrt(dx * dx + dy * dy)
    return np.clip(radius_px - d + 0.5, 0, 1)

@functools.lru_cache(None)
def video_frames(path, w=W, h=H):
    cmd = ['ffmpeg', '-v', 'error', '-i', path, '-vf',
           f'scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}',
           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)

def vframe(path, t, fps=30.0):
    fr = video_frames(path)
    i = min(len(fr) - 1, max(0, int(t * fps)))
    return fr[i].astype(np.float32) / 255.0

@functools.lru_cache(None)
def seq_list(folder):
    return sorted(glob.glob(os.path.join(folder, '*.png')))

@functools.lru_cache(256)
def seq_rgba(path):
    return load_rgba(path)

def seqframe(folder, t, fps=30.0):
    fs = seq_list(folder)
    i = min(len(fs) - 1, max(0, int(t * fps)))
    return seq_rgba(fs[i])

def res(pkg, *parts):
    g = glob.glob(os.path.join(pkg.root, *parts))
    return g[0] if g else None

def shake(t, amp_px, freq=6.0, seed=1):
    if amp_px < 0.1: return 0.0, 0.0
    return (amp_px * (math.sin(t * freq * 6.28 + seed) * 0.6 + math.sin(t * freq * 13.1 + 2 * seed) * 0.4),
            amp_px * (math.cos(t * freq * 5.3 + 3 * seed) * 0.6 + math.sin(t * freq * 11.7 + seed) * 0.4))

# ---------------------------------------------------------------- переходи
def t00(P, A, B, t):  # Хлопок и притяжение
    sx = W / 504.0
    base = np.array([253.195, 448.574])
    jx, jy = (P.k('LumiLayer_2504-trs-blend', 'p0_position', t) - np.r_[base, 0])[:2] * sx
    bs = P.k('LumiLayer_2505-trs', 'scale', t)[0] / 100
    bx = (P.k('LumiLayer_2505-trs', 'position', t)[0] + 1.195) * sx
    out = affine(B, scale=bs, dx=bx + jx, dy=jy)
    if t < 1.5:
        a_s = P.k('LumiLayer_2504-trs-blend', 'scale', t)[0] / 100
        ax = (P.k('LumiLayer_2504-trs-blend', 'position', t)[0] + 1.195) * sx
        top, al = affine(A, scale=a_s, dx=ax + jx, dy=jy, alpha=True)
        out = over(out, top, al)
    out = hblur(out, P.k('LumiDirectionalBlurs_2503-effect0', 'blurIntensity', t) * sx * 0.45)
    if 0.3 <= t < 0.367:
        out = np.ones_like(out)
    return out

def t01(P, A, B, t):  # Горизонтальное размытие
    op = P.k('LumiLayer_27', 'opacity', t) / 100
    out = over(B, A, op)
    out = hblur(out, P.k('LumiDirectionalBlurs_200', 'blurIntensity', t) * W / 1280 * 1.2)
    return exposure(out, P.k('LumiExposure_200', 'exposure', t), P.k('LumiExposure_200', 'grayscaleCorrection', t))

def t02(P, A, B, t):  # Засветка камеры
    if t < 0.533: out = A
    else: out = affine(B, scale=P.k('LumiLayer_46', 'p0_scale', t)[0] / 100)
    out = glow(out, P.k('LumiGlow_49', 'glowIntensity', t), 0.6, 50 * W / 1000)
    lt = vframe(res(P, 'resource/video/Light.mp4'), P.k('LumiAnimSeqLoadAndCrop_1703', 'seqTime', t), 29.97)
    return add(out, lt, P.k('LumiLayer_1703', 'opacity', t) / 100)

def _light_xfade(P, A, B, t, vid, b_node, a_node, light_node):
    ob = P.k(b_node, 'opacity', t) / 100
    oa = P.k(a_node, 'opacity', t) / 100
    out = over(B * ob, A, oa)
    lo = P.k(light_node, 'opacity', t, 100.0) / 100
    seq_node = [n for n in P.d['ae_attribute'] if n.startswith('LumiAnimSeqLoadAndCrop')][0]
    lt = vframe(res(P, 'resource/video', vid), P.k(seq_node, 'seqTime', t), 30)
    return screen(out, lt, lo)

def t03(P, A, B, t):  # Быстрое ослепление
    return _light_xfade(P, A, B, t, 'light4.mp4', 'LumiLayer_315', 'LumiLayer_316', 'LumiLayer_378')

def t04(P, A, B, t):  # Мигающий зум
    out = over(B, A, P.k('LumiLayer_27', 'opacity', t) / 100)
    return bokeh(out, P.k('LumiBokehBlur_200', 'sample', t) * W / 1280 * 0.9)

def t05(P, A, B, t):  # Сожженный портал
    a = barrel(A, P.k('LumiOpticsCompensation_205', 'fov', t) / 100 * 0.35)
    b = affine(B, scale=0.6, rot=-24)
    mrgb, ma = seqframe(os.path.join(P.root, 'resource/seq/Mask'), t, 30)
    out = over(b, a, ma)
    prgb, pa = seqframe(os.path.join(P.root, 'resource/seq/Portal'), t, 30)
    out = over(out, prgb, pa)
    rot = P.k('LumiMotionBlur2D_373', 'rotate', t)
    sc = P.k('LumiMotionBlur2D_373', 'scale_x', t)
    dx, dy = shake(t, P.k('LumiSShake_373', 'ampRatio', t) * 120, 6)
    return affine(out, scale=sc, rot=rot, dx=dx, dy=dy)

def t06(P, A, B, t):  # Вспышка жара
    return _light_xfade(P, A, B, t, 'light3.mp4', 'LumiLayer_296', 'LumiLayer_297', 'LumiLayer_383')

def t07(P, A, B, t):  # Кадры с монтажа
    out = over(A, B, P.k('LumiLayer_50', 'opacity', t) / 100)
    # «плівковий» сигнал: зниження якості, різкість, кольоровий зсув, зерно
    small = np.asarray(Image.fromarray((out * 255).astype(np.uint8)).resize((W // 3, H // 3), Image.BILINEAR)
                       .resize((W, H), Image.BILINEAR), np.float32) / 255
    out = np.clip(small * 1.35 - blur(small, 2) * 0.35, 0, 1)
    out = chroma_shift(out, 2.0)
    rng = np.random.default_rng(int(t * 1000))
    out = np.clip(out + (rng.standard_normal((H, W, 1)).astype(np.float32) * 0.035), 0, 1)
    out = vignette(out, 0.52, 0.73, 0.79)
    film = seq_list(os.path.join(P.root, 'resource/seq', os.listdir(os.path.join(P.root, 'resource/seq'))[0]))
    fr = to_f(fit_cover(Image.open(film[min(len(film) - 1, int(t * 25))])))
    return screen(out, fr)

def t08(P, A, B, t):  # Увеличение центра
    k = min(5, int(t / (P.dur / 6)))
    s = [0, .2, .4, .6, .8, 1.0][k]
    if s <= 0: return A
    top, al = affine(B, scale=s, alpha=True)
    return over(A, top, al)

def t09(P, A, B, t):  # Мерцающее преобразование
    out = over(B, A, P.k('LumiLayer_27', 'opacity', t) / 100)
    out = blur(out, P.k('LumiGaussianBlur_200', 'blurIntensity', t) * W / 1280 * 0.45)
    fl = vframe(res(P, 'resource/video/Flare.mp4'), P.k('LumiAnimSeqLoadAndCrop_203', 'seqTime', t), 30)
    return add(out, fl)

def t10(P, A, B, t):  # Глубокая дрожь
    s = W / 1080
    ax = (P.k('LumiLayer_1803', 'position', t)[0] - 540) * s * 1.6
    bx = (P.k('LumiLayer_1802', 'position', t)[0] - 540) * s * 1.6
    hx = P.k('LumiDisplacementMap_202', 'horizontalIntensity', t)
    vy = P.k('LumiDisplacementMap_202', 'verticalIntensity', t)
    a = affine(A, dx=ax, mode='mirror')
    b, ba = affine(B, dx=bx + hx * W * 0.5, dy=vy * H * 0.5, alpha=True)
    if bx + hx * W * 0.5 < W * 0.02:  # після приземлення B закриває кадр повністю
        b = affine(B, dx=bx + hx * W * 0.5, dy=vy * H * 0.5, mode='mirror'); ba = np.ones_like(ba)
    out = over(a, b, ba)
    out = chroma_shift(out, P.k('LumiChromaticAberration_1801', 'offsetX', t) * 40 * s)
    out = hblur(out, P.k('LumiGaussianBlur_1801', 'blurIntensity', t) * s * 2.2)
    return exposure(out, P.k('LumiExposure_1801', 'exposure', t))

def t11(P, A, B, t):  # Рассеивание вверх
    a = zoom_blur(A, P.k('LumiRadialBlur_27', 'amount', t), 0.5, 0.0)
    amp = P.k('LumiWaveWarp_27', 'amplitude', t) * W / 1280
    if amp > 0.2:
        yy, xx = grid()
        a = sample(a, yy + amp * np.sin((xx / (450 * W / 1280) + t * 2) * 6.283), xx)
    pos = P.k('LumiLayer_27', 'position', t)
    sc = P.k('LumiLayer_27', 'scale', t)[0] / 100
    top, al = affine(a, scale=sc, dy=(pos[1] - 360) * H / 720, cy=0 + H / 2, alpha=True)
    out = over(B, top, al * P.k('LumiLayer_27', 'opacity', t) / 100)
    return exposure(out, P.k('LumiExposure_195', 'exposure', t))

def t12(P, A, B, t):  # Искажение ускорения
    n = 'LumiLayer_175547097703'
    if t < 0.458:
        p = P.k(n, 'position', t); s = P.k(n, 'scale', t)[0] / 100; r = P.k(n, 'rotation', t)
        out = affine(A, scale=s, rot=r, dx=(p[0] - 540) * W / 1080, dy=(p[1] - 540) * W / 1080)
    else:
        out = B
    if 0.083 <= t <= 1.017:
        e = 'LumiRadialBlur_175547097701'
        out = zoom_blur(out, P.k(e, 'amount', t), n=12)
        conv = P.k('LumiCCLens_175547097701', 'convergence', t)
        b3 = P.k('LumiWarp_175547097701-effect3', 'bend', t)
        b4 = P.k('LumiWarp_175547097701-effect4', 'bend', t)
        out = barrel(out, conv / 100 * 1.6 + (b3 + b4) / 100 * -0.25)
        out = exposure(out, P.k('LumiExposure_175547097701', 'exposure', t))
    return out

def _mb(fn, t, dt=1 / 60, n=5):
    acc = 0
    for i in range(n): acc = acc + fn(t - dt * i / (n - 1))
    return acc / n

def t13(P, A, B, t):  # Прыжок и отскок
    if t < 0.333:
        def f(tt):
            tt = max(tt, 0)
            s = P.k('LumiMotionBlur2D_3419', 'scale_x', tt)
            r = P.k('LumiLayer_3433', 'rotation', tt)
            img = barrel(A, P.k('LumiOpticsCompensation_3419', 'fov', tt) / 125 * 0.6)
            return affine(img, scale=s, rot=r)
    else:
        def f(tt):
            s = P.k('LumiMotionBlur2D_3397', 'scale_x', tt)
            r = P.k('LumiLayer_3411', 'rotation', tt)
            img = barrel(B, P.k('LumiOpticsCompensation_3397', 'fov', tt) / 170 * 0.8)
            return affine(img, scale=s, rot=r)
    return _mb(f, t, 1 / 30, 5)

def t14(P, A, B, t):  # Мутация улья
    if t >= 0.867: return B
    m = vframe(res(P, 'resource/video/liubianxingv3.mp4'), t, 30).mean(2)
    d = 6 * W / 1080
    sh = ndi.shift(m, (d, -d), order=1, mode='nearest')
    out = A * (1 - 0.8 * np.clip(sh - m, 0, 1))[..., None]
    return over(out, B, m)

def t15(P, A, B, t):  # Снимки
    # фон: B на відстані, повернутий, затемнений і розмитий
    pz = P.k('LumiLayer_9404', 'position', t); ori = P.k('LumiLayer_9404', 'orientation', t)
    br = P.k('LumiBrightness_9404', 'brightnessIntensity', t)
    bimg = np.clip(B * (1 + br), 0, 1)
    rr = P.k('LumiRoundCorner_9404', 'radius', t)
    b_rgb, b_a = persp(bimg, ori[0], ori[1], ori[2], 0, (pz[1] - 720) * H / 1440, pz[2] * W / 1080)
    b_a = b_a * (round_mask(1, 1, rr * W / 1080 * 2) if rr > 0.5 else 1)
    out = b_rgb * b_a[..., None]
    out = blur(out, P.k('LumiGaussianBlur_9403', 'blurIntensity', t) * W / 1080 * 0.6)
    if t < 0.967:
        if t < 0.267:
            card, ca = A, np.ones((H, W), np.float32)
        else:
            u = min(1, (t - 0.267) / 0.166)
            img = desat(A, -P.k('LumiSaturation_11902', 'saturationIntensity', t))
            c = P.k('LumiContrast_11902', 'contrastIntensity', t)
            img = np.clip((img - 0.5) * c + 0.5, 0, 1)
            img = vignette(img, P.k('LumiVignette_11902', 'amount', t), 0.5, 0.8)
            s = P.k('LumiLayer_11901', 'scale', t); p = P.k('LumiLayer_11901', 'position', t)
            inner, ia = affine(img, scale=(s[0] / 100, s[1] / 100), dy=(p[1] - 720) * H / 1440 * 1.0, alpha=True)
            paper = np.full_like(A, 0xE9 / 255)
            card = over(paper, inner, ia * round_mask(s[0] / 100, s[1] / 100, 6, cy=H / 2 + (p[1] - 720) * H / 1440))
            ca = round_mask(1, 1, 9 * W / 1080 * u * 2)
        pos = P.k('LumiMotionBlur3D_9402', 'position', t)
        rx = P.k('LumiMotionBlur3D_9402', 'rotation_x', t)
        ry = P.k('LumiMotionBlur3D_9402', 'rotation_y', t)
        rz = P.k('LumiMotionBlur3D_9402', 'rotation_z', t)
        c4, c_a = persp(np.dstack([card, ca]), rx, ry, rz, (pos[0] - 0.5) * W, (pos[1] - 0.5) * H, pos[2] * W * 1.1)
        out = over(out, c4[..., :3], c_a * c4[..., 3])
    g = P.k('LumiDeepGlow_9401', 'exposure', t)
    if g > 0.01:
        out = np.clip(out + blur(out, 60) * g * 1.2 + g * 0.25, 0, 1)
    return out

def _tunnel(tex, depth, rotz):
    """Погляд у коробку: на стінах і в глибині та сама картинка."""
    yy, xx = grid()
    u = (xx - W / 2) / (W / 2); v = (yy - H / 2) / (H / 2)
    if abs(rotz) > 0.01:
        c, s = math.cos(math.radians(rotz)), math.sin(math.radians(rotz))
        u, v = c * u + s * v * H / W, (-s * u * W / H + c * v)
    sback = 1 - 0.72 * depth
    r = np.maximum(np.abs(u), np.abs(v))
    tu = np.where(r <= sback, u / sback, 0); tv = np.where(r <= sback, v / sback, 0)
    if depth > 0.001:
        q = np.clip((1 / np.maximum(r, 1e-3) - 1) / (1 / sback - 1), 0, 1)  # 0 біля краю екрана, 1 у глибині
        side = np.abs(u) >= np.abs(v)
        wall_u = np.where(side, np.sign(u) * (1 - q), u / np.maximum(r, 1e-3))
        wall_v = np.where(side, v / np.maximum(r, 1e-3), np.sign(v) * (1 - q))
        inwall = r > sback
        tu = np.where(inwall, wall_u, tu); tv = np.where(inwall, wall_v, tv)
    xs = (tu + 1) * W / 2; ys = (tv + 1) * tex.shape[0] / 2 if tex.shape[0] == H else (tv + 1) * H / 2
    return xs, ys

def t16(P, A, B, t):  # Кошмарное искажение
    def styl(img, vnode, snode):
        img = desat(img, -P.k(snode, 'saturationIntensity', t))
        return vignette(img, P.k(vnode, 'amount', t), 0.45, 0.8)
    a = styl(A, 'LumiVignette_6001', 'LumiSaturation_6001')
    b = styl(B, 'LumiVignette_9301', 'LumiSaturation_9301')
    da = 1 - P.k('LumiCube_103', 'position', t)[2]   # A: z 1->0 = входимо в коробку
    db = 1 - P.k('LumiCube_102', 'position', t)[2]   # B: z 0->1 = виходимо
    ya = (P.k('LumiLayer_103', 'position', t)[1] - 500) / 1000  # 0 -> 1 (A їде вниз)
    depth = da if t < 1.0 else db
    rz = P.k('LumiCube_103', 'rotateZ', t) if t < 1.0 else P.k('LumiCube_102', 'rotateZ', t)
    xs, ys = _tunnel(a, depth, rz)
    # вертикальна стрічка [B; A], зсув на ya висоти кадру
    strip = np.concatenate([b, a], 0)
    out = sample(strip, ys + H * (1 - ya), xs, mode='mirror')
    leak = seq_list(os.path.join(P.root, 'resource/seq/heng'))
    fr = to_f(fit_cover(Image.open(leak[min(len(leak) - 1, int(t * 30))])))
    return lighten(out, fr)

def t17(P, A, B, t):  # Глубокий поворот
    if t < 0.267:
        out = affine(A, rot=P.k('LumiLayer_1803', 'rotation', t), mode='mirror')
    else:
        hx = P.k('LumiDisplacementMap_202', 'horizontalIntensity', t)
        vy = P.k('LumiDisplacementMap_202', 'verticalIntensity', t)
        out = affine(B, rot=P.k('LumiLayer_1802', 'rotation', t), dx=hx * W * 0.4, dy=vy * H * 0.4, mode='mirror')
    g = P.k('LumiBCC_Prism_1801', 'globalTransform', t)
    if g > 0.2:
        sp = zoom_blur(out, g * 3, spin=True, n=8)
        r = affine(sp, scale=1 + g * 0.006, rot=g * 0.5, mode='mirror')[..., 0]
        bb = affine(sp, scale=1 - g * 0.006, rot=-g * 0.5, mode='mirror')[..., 2]
        out = np.dstack([r, sp[..., 1], bb])
    return exposure(out, P.k('LumiExposure_1801', 'exposure', t))

def t18(P, A, B, t):  # Космический корабль
    return _light_xfade(P, A, B, t, 'light1.mp4', 'LumiLayer_41', 'LumiLayer_42', 'LumiLayer_364')

def t19(P, A, B, t):  # Закрытый горизонт
    out = A if t < 0.833 else B
    if 0.667 <= t <= 1.1:
        out = blur(out, P.k('LumiGaussianBlur_509', 'blurIntensity', t) * W / 720 * 0.5)
        out = exposure(out, P.k('LumiDeepGlow_509', 'exposure', t) * 0.35)
        out = barrel(out, P.k('LumiWarp_509', 'bend', t) / 100 * 0.6)
        out = out * (1 + P.k('LumiFlicker_509', 'amp0', t) * math.sin(t * 60))
    if 0.833 <= t <= 1.033:
        dx, dy = shake(t, P.k('LumiSShake_503', 'ampRatio', t) * 40, 30)
        out = affine(out, dx=dx, dy=dy)
    # шторки: край верхньої — y573, нижньої — y561 (дизайн 720x1280 по висоті)
    top = P.k('LumiLayer_573', 'position', t)[1] / 1280 * H
    bot = P.k('LumiLayer_561', 'position', t)[1] / 1280 * H
    yy = grid()[0]
    m = ((yy < top) | (yy > bot)).astype(np.float32)
    out = out * (1 - m)[..., None]
    if bot - top < H * 0.06:
        line = np.exp(-((yy - (top + bot) / 2) / 1.5) ** 2) * (1 - (bot - top) / (H * 0.06))
        out = np.maximum(out, line[..., None])
    return np.clip(out, 0, 1)

FUNCS = [t00, t01, t02, t03, t04, t05, t06, t07, t08, t09, t10, t11, t12, t13, t14, t15, t16, t17, t18, t19]
