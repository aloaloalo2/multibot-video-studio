"""12 ефектів-шарів CapCut: 6 шумів і 6 трендових. f(root, img, t) -> кадр."""
import os, glob, math, subprocess, functools
import numpy as np
from PIL import Image
from ctrans import *  # noqa
from ctrans2 import luma, ramp, ease, warp_noise

def _af(root):
    return glob.glob(os.path.join(root, 'x', '*', ''))[0] if not root.endswith('/') else glob.glob(root + 'x/*/')[0]

@functools.lru_cache(None)
def _seq(folder, pattern='*.png'):
    fs = sorted(glob.glob(os.path.join(folder, pattern)), key=lambda f: int(''.join(c for c in os.path.basename(f) if c.isdigit()) or 0))
    return [to_f(fit_cover(Image.open(f).convert('RGB'))) for f in fs]

@functools.lru_cache(None)
def _sbs(path):
    """Відео «колір | альфа» поруч: повертає (rgb, alpha) кадри під наш розмір."""
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         capture_output=True, check=True).stdout
    w, h = map(int, subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
                                    '-of', 'csv=p=0', path], capture_output=True, text=True).stdout.strip().split(','))
    fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)
    out = []
    for f in fr:
        c = Image.fromarray(f[:, :w // 2]); a = Image.fromarray(f[:, w // 2:]).convert('L')
        out.append((to_f(fit_cover(c)), np.asarray(fit_cover(a), np.float32) / 255))
    return out

def multiply(a, b, o=1.0): return a + (a * b - a) * o
def overlay(a, b, o=1.0):
    r = np.where(a < 0.5, 2 * a * b, 1 - 2 * (1 - a) * (1 - b))
    return a + (r - a) * o

def fx00(root, img, t):  # Шум 1: плівкова текстура, множення
    fr = _seq(os.path.join(root, 'image'))
    return multiply(img, fr[int(t * 15) % len(fr)])

def fx01(root, img, t):  # Шум и пыль: тьмяніша холодна гама + пил із відео
    o = np.clip((img - 0.5) * (1 - 0.42 * 0.6) + 0.5 - 0.29 * 0.25, 0, 1)
    o = desat(o, 0.2)
    o = o * np.array([1 - 0.17 * 0.25, 1, 1 + 0.17 * 0.25], np.float32)
    fr = _sbs(glob.glob(os.path.join(root, 'resource/video/Landscape*.mp4'))[0])
    c, a = fr[int(t * 30) % len(fr)]
    return np.clip(over(o, c, a), 0, 1)

def fx02(root, img, t):  # Черный шум: множення
    fr = _seq(os.path.join(root, 'image'))
    return multiply(img, fr[int(t * 15) % len(fr)])

@functools.lru_cache(None)
def _grain(root):
    im = Image.open(glob.glob(os.path.join(root, 'image', '*.png'))[0]).convert('RGBA')
    a = np.asarray(im, np.float32) / 255
    return a

def fx03(root, img, t):  # Зернистость: зерно з випадковим зсувом щокадру
    g = _grain(root)
    k = int(t * 24)
    rng = np.random.default_rng(k)
    y = rng.integers(0, g.shape[0] - H); x = rng.integers(0, g.shape[1] - W)
    tile = g[y:y + H, x:x + W]
    return overlay(img, tile[..., :3], tile[..., 3:4] * 0.9)

def fx04(root, img, t):  # Белый шум
    fr = _sbs(os.path.join(root, 'resource/video/Landscape.mp4'))
    c, a = fr[int(t * 30) % len(fr)]
    return over(img, c, a)

@functools.lru_cache(None)
def _vid(path):
    return [f.astype(np.float32) / 255 for f in video_frames(path)]

def fx05(root, img, t):  # VHS-шум: відео без альфи, «unmult» (яскравість = прозорість)
    fr = _vid(os.path.join(root, 'resource/video/VHSDistortion.mp4'))
    c = fr[int(t * 30) % len(fr)]
    a = c.max(2, keepdims=True)
    col = c / np.maximum(a, 1e-3)
    return over(img, col, a[..., 0])

def fx06(root, img, t):  # Скользящий трепет: вступ картки з хвилею
    D = 2.97
    t = t % D
    out = np.zeros_like(img)
    if t < 2.0:
        x = 1004 + (392 - 1004) * ease(ramp(t, 0, 1.0))
        s = 0.5 + 0.5 * ease(ramp(t, 1.0, 2.0))
        amp = 10 * (1 - ramp(t, 1.5, 2.0)) * W / 784
        yy, xx = grid()
        w = sample(img, yy + amp * np.sin(xx / 60 + t * 6), xx)
        card, a = affine(w, scale=s * (0.45 + 0.55 * ramp(t, 1.0, 2.0)), dx=(x - 392) * W / 784 * 0.6, alpha=True)
        out = over(out, card, a * ramp(t, 0.0, 0.15))
    else:
        u = ramp(t, 2.0, 2.5)
        out = hblur(affine(img, scale=1.25 - 0.25 * ease(u)), 50 * (1 - u) * W / 784)
        out = exposure(out, 1 - u)
    return out

def fx07(root, img, t):  # Стеклянный браслет: склянний браслет на чорному, потім кадр
    t = t % 3.0
    fr = _vid(glob.glob(os.path.join(root, 'resource/video/*.mp4'))[0])
    c = fr[int(t * 30) % len(fr)]
    bgl = np.median(c[:20, :20].reshape(-1, 3), 0)
    c = np.clip((c - bgl - 0.03) / (1 - bgl), 0, 1)
    base = img * ease(ramp(t, 0.6, 1.9))
    out = screen(base, c, 0.66 if t < 1.92 else 0.66 * (1 - ramp(t, 1.92, 3.0)))
    return glow(out, 0.5 if t < 1.92 else 0.5 * (1 - ramp(t, 1.92, 3.0)), 0.75, 30)

def fx08(root, img, t):  # Звёздный круиз
    fr = _sbs(os.path.join(root, 'resource/video/landscape.mp4'))
    c, a = fr[int(t * 30) % len(fr)]
    return over(img, c, a)

@functools.lru_cache(None)
def _player(root):
    fs = [f for f in glob.glob(os.path.join(root, 'resource/images/*.png')) if 'Solid' not in f and 'mask' not in f]
    ims = [Image.open(f).convert('RGBA') for f in sorted(fs)]
    return ims

def fx09(root, img, t):  # Игрок 3: плашка «музика грає»
    out = img * (0.25 + 0.75 * ease(ramp(t % 3, 0, 0.35)))
    out = vignette(out, 0.35, 0.6, 0.8)
    for im in _player(root):
        sz = int(H * 0.62)
        p = im.resize((sz, sz), Image.LANCZOS)
        a = np.zeros((H, W, 4), np.float32)
        x0, y0 = int(W * 0.02), int(-H * 0.12)
        arr = np.asarray(p, np.float32) / 255
        ys, xs = slice(max(0, y0), y0 + sz), slice(x0, x0 + sz)
        a[ys, xs] = arr[max(0, -y0):, :]
        out = over(out, a[..., :3], a[..., 3] * ease(ramp(t % 3, 0.2, 0.5)))
    return out

def fx10(root, img, t):  # Розовая вселенная (без виділення людини: блискітки поверх кадру)
    fr = _sbs(os.path.join(root, 'resource/video/Landscape.mp4'))
    c, a = fr[int(t * 30) % len(fr)]
    base = vignette(affine(img, scale=1.12), 0.32, 0.6, 0.8)
    return screen(base, c * a[..., None], 0.85)

def fx11(root, img, t):  # Зеленый CRT
    g = luma(img)[..., None]
    col = np.clip(g * np.array([0.35, 1.05, 0.55], np.float32) + np.array([0.02, 0.08, 0.04], np.float32), 0, 1)
    yy, xx = grid()
    scan = 0.82 + 0.18 * (np.sin(yy * math.pi / 2.0 + t * 20) > 0)
    col = col * scan[..., None]
    col = barrel(col, 0.18)
    col = vignette(col, 0.85, 0.55, 0.7)
    m = round_mask(0.94, 0.92, 40)
    rng = np.random.default_rng(int(t * 30))
    col = col + rng.standard_normal((H, W, 1)).astype(np.float32) * 0.03
    return np.clip(col * m[..., None], 0, 1)

FX = [fx00, fx01, fx02, fx03, fx04, fx05, fx06, fx07, fx08, fx09, fx10, fx11]


# ---------------------------------------------------------------- накладки з прозорістю (для студії)
# Ефект-накладка дає (колір, альфа): рендер студії кладе такий шар звичайним змішуванням поверх усього, що нижче,
# тому ефект однаково працює на одному кадрі й доріжкою над таймлайном. «Множення» на текстуру m точно дорівнює
# чорному кольору з альфою 1-m; «перекриття» зерна наближено білим/чорним з альфою |g-0.5|.
BLACK = None

def _black():
    return np.zeros((H, W, 3), np.float32)

def ov00(root, t):  # Шум 1
    fr = _seq(os.path.join(root, 'image'))
    m = fr[int(t * 15) % len(fr)]
    return _black(), 1 - luma(m)

def ov01(root, t):  # Шум і пил: холодне затемнення + пил
    tint = np.ones((H, W, 3), np.float32) * np.array([0.10, 0.12, 0.16], np.float32)
    ta = np.full((H, W), 0.22, np.float32)
    fr = _sbs(glob.glob(os.path.join(root, 'resource/video/Landscape*.mp4'))[0])
    c, a = fr[int(t * 30) % len(fr)]
    out_a = a + ta * (1 - a)
    rgb = (c * a[..., None] + tint * (ta * (1 - a))[..., None]) / np.maximum(out_a, 1e-4)[..., None]
    return rgb, out_a

def ov02(root, t):  # Чорний шум
    fr = _seq(os.path.join(root, 'image'))
    m = fr[int(t * 15) % len(fr)]
    return _black(), 1 - luma(m)

def ov03(root, t):  # Зернистість
    g = _grain(root)
    rng = np.random.default_rng(int(t * 24))
    y = rng.integers(0, max(1, g.shape[0] - H)); x = rng.integers(0, max(1, g.shape[1] - W))
    tile = g[y:y + H, x:x + W]
    if tile.shape[0] < H or tile.shape[1] < W:
        tile = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize((W, H)), np.float32) / 255
    lg = luma(tile[..., :3])
    rgb = np.where((lg > 0.5)[..., None], 1.0, 0.0).astype(np.float32) * np.ones((1, 1, 3), np.float32)
    return rgb, np.clip(np.abs(lg - 0.5) * 2 * tile[..., 3] * 0.45, 0, 1)

def ov04(root, t):  # Білий шум
    fr = _sbs(os.path.join(root, 'resource/video/Landscape.mp4'))
    return fr[int(t * 30) % len(fr)]

def ov05(root, t):  # VHS-шум
    fr = _vid(os.path.join(root, 'resource/video/VHSDistortion.mp4'))
    c = fr[int(t * 30) % len(fr)]
    a = c.max(2)
    return c / np.maximum(a, 1e-3)[..., None], a

def ov08(root, t):  # Зоряний круїз
    fr = _sbs(os.path.join(root, 'resource/video/landscape.mp4'))
    return fr[int(t * 30) % len(fr)]

def ov09(root, t, intro=True):  # Плеєр 3: затемнення на вході й плашка плеєра
    a = np.zeros((H, W), np.float32); rgb = _black()
    if intro:
        a = np.full((H, W), 0.75 * (1 - ease(ramp(t, 0, 0.35))), np.float32)
    yy, xx = grid()
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
    a = a + (1 - a) * 0.35 * np.clip((r - 0.3) / 0.6, 0, 1) ** 2
    k = ease(ramp(t, 0.2, 0.5)) if intro else 1.0
    for im in _player(root):
        sz = int(H * 0.62)
        arr = np.asarray(im.resize((sz, sz), Image.LANCZOS), np.float32) / 255
        x0, y0 = int(W * 0.02), int(-H * 0.12)
        plate = np.zeros((H, W, 4), np.float32)
        plate[max(0, y0):y0 + sz, x0:x0 + sz] = arr[max(0, -y0):, :]
        pa = plate[..., 3] * k
        rgb = (plate[..., :3] * pa[..., None] + rgb * (a * (1 - pa))[..., None]) / np.maximum(pa + a * (1 - pa), 1e-4)[..., None]
        a = pa + a * (1 - pa)
    return rgb, a

def ov10(root, t):  # Рожевий всесвіт: блискітки й легке затемнення країв
    fr = _sbs(os.path.join(root, 'resource/video/Landscape.mp4'))
    c, a = fr[int(t * 30) % len(fr)]
    return c, np.clip(a * luma(c) * 1.4, 0, 1)

@functools.lru_cache(None)
def _rgba_seq(folder):
    out = []
    for f in sorted(glob.glob(os.path.join(folder, '*.png'))):
        a = np.asarray(fit_cover(Image.open(f).convert('RGBA')), np.float32) / 255
        out.append((a[..., :3], a[..., 3]))
    return out

def ov12(root, t):  # Шум 2: screen з послідовністю й multiply з папером, зведені в один шар прозорості (10 кадрів/с)
    fr = _rgba_seq(os.path.join(root, 'layer'))
    return fr[int(t * 10) % len(fr)]

# індекс ефекту -> (функція накладки, довжина петлі в секундах, тривалість вступу або 0)
OVERLAYS = {0: (ov00, 17 / 15, 0), 1: (ov01, 3.0, 0), 2: (ov02, 28 / 15, 0), 3: (ov03, 2.0, 0), 4: (ov04, 3.0, 0),
            5: (ov05, 3.0, 0), 12: (ov12, 2.8, 0), 8: (ov08, 3.0, 0), 9: (ov09, 1.0, 1.0), 10: (ov10, 3.0, 0)}
# ефекти, що змінюють сам кадр: (функція, природна тривалість анімації або 0 для безперервного)
CONTENT = {6: (fx06, 2.97), 7: (fx07, 3.0), 11: (fx11, 0)}
