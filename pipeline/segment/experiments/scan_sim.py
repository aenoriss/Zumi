"""Offline simulation of the XR scanner's automatic page capture (apps/xr/Assets/Zumi/Flow/ZumiScanner.cs).

What it does
  1. Renders scripted 10-page scanning sessions as the scanner would sample them: a desk plane (2 px/mm) with the
     pencil pages, a hand (skin occluder + soft shadow) carrying, placing, hovering, swapping; then a Quest-3-like
     passthrough camera (1280x960 class: 1.45-2.4 camera px per mm, perspective, optics/motion blur, auto-exposure
     with lag/steps/flicker, white-balance cast, black lift, YUV420 chroma, noise, 8-bit), read back as sRGB or as
     linear bytes; then the guide warp exactly as ZumiWarp does it (one bilinear tap per output pixel, no mips) at
     2x the sample size, with a pose-registration error, averaged 2x2. Each sample covers the guide plus a ring of
     desk around it (96x134: the guide is the central 64x90, cols 16..79, rows 22..111; row 0 is the near edge).
  2. Runs detectors over the 10 Hz samples with the scanner's blind window (no samples for 1.3 s after a capture:
     the sweep and the flight) and scores them against ground truth (which page lies on top, whether a hand is over
     the guide).

Usage (pipeline/segment/.venv/Scripts/python):
  python scan_sim.py render            render and cache every session (about a minute on 16 cores)
  python scan_sim.py eval [det ...]    metrics per condition for the named detectors (default: all)
  python scan_sim.py sheet COND [t0]   contact sheet of a session's samples, to look at
  python scan_sim.py explain DET COND [t0 t1]   per-sample ground truth, state and measures
  python scan_sim.py replay FILE [DET] a headset recording ([float32 time][192*268*4 RGBA] per sample)
  SCAN_SIM_SEED=1 ...                  a held-out set of sessions (render it first)

Iterations (eval rows): v0_baseline (ZumiScanner today), it1..it5; it5_final = PageDetector = ZumiPageDetector.cs.
"""
import math
import os
import sys
import tempfile
from multiprocessing import Pool

import cv2
import numpy as np

PAGES_DIR = r"C:\Users\Usuario\Downloads\Paginas finales Comic\Lapices"
# SCAN_SIM_SEED=1 renders a held-out set of sessions (other pages order, desks, light, jitter) into its own cache
SEED = int(os.environ.get("SCAN_SIM_SEED", "0"))
CACHE = os.environ.get("SCAN_SIM_CACHE", os.path.join(tempfile.gettempdir(), "zumi_scan_sim" + (f"_{SEED}" if SEED else "")))

# ---- geometry -------------------------------------------------------------------------------------------------
GW, GH = 210.0, 297.0          # the guide, mm (A4)
SW, SH = 64, 90                 # the guide's sample, px
RX, RY = 16, 22                 # the desk ring sampled around it, px each side
FW, FH = SW + 2 * RX, SH + 2 * RY   # the full sample: 96 x 134
RING_MM = (RX * GW / SW, RY * GH / SH)  # 52.5 mm, 72.6 mm
P = 2.0                         # plane px per mm
MX, MY = 130.0, 160.0           # plane margin around the guide, mm
PW, PH = int((GW + 2 * MX) * P), int((GH + 2 * MY) * P)
GC = (MX + GW / 2, MY + GH / 2)  # the guide's centre on the plane, mm
DT = 0.1                        # sample interval, s
BLIND = 1.3                     # scanning + flying: the scanner takes no samples, s

# ---- conditions ---------------------------------------------------------------------------------------------
BASE = dict(desk="mid_wood", light=(1.0, 0.93, 0.85), level=1.0, gmax=6.0, noise=0.012, black=0.04, cast=0.04,
            readback="srgb", jitter=0.8, offset=3.0, burst=0.01, ae_steps=0.0, flicker=0.0, scale=(1.6, 2.2),
            ink=(0.45, 0.65))
CONDITIONS = {
    "mid_wood":        dict(),
    "dark_wood_warm":  dict(desk="dark_wood", light=(1.0, 0.82, 0.60), cast=0.06),
    "grey_dim":        dict(desk="grey", level=0.35, gmax=3.0, noise=0.025, black=0.07),
    "white_desk":      dict(desk="white"),
    "cluttered_ae":    dict(desk="cluttered", ae_steps=0.04, flicker=0.03),
    "mid_wood_linear": dict(readback="linear"),
    "dark_linear_dim": dict(desk="dark_wood", readback="linear", level=0.4, gmax=3.0, noise=0.022),
    "restless_far":    dict(jitter=2.0, offset=6.0, burst=0.05, scale=(1.4, 1.6), noise=0.02),
}


def cond(name):
    c = dict(BASE)
    c.update(CONDITIONS[name])
    return c


# ---- assets -------------------------------------------------------------------------------------------------
_pages = None


def pages():
    """The ten pencil pages as plane-scale grey images (1 paper, 0 graphite), 420 x 594."""
    global _pages
    if _pages is None:
        _pages = []
        for i in range(1, 11):
            a = cv2.imdecode(np.fromfile(os.path.join(PAGES_DIR, f"Pagina lapiz {i}.jpg"), np.uint8), cv2.IMREAD_GRAYSCALE)
            _pages.append(cv2.resize(a, (int(GW * P), int(GH * P)), interpolation=cv2.INTER_AREA).astype(np.float32) / 255)
    return _pages


def make_desk(kind, rng):
    h, w = PH, PW
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    def grain(scale):
        n = cv2.resize(rng.standard_normal((h // 40 + 2, 6)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
        fine = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), 1.2)
        stripes = np.sin(yy / (7 + 3 * n) + 0.8 * n) * 0.5 + 0.2 * fine
        return 1 + scale * stripes
    if kind == "dark_wood":
        d = np.array([0.10, 0.06, 0.035], np.float32) * grain(0.3)[..., None]
    elif kind == "mid_wood":
        d = np.array([0.36, 0.23, 0.13], np.float32) * grain(0.2)[..., None]
    elif kind == "grey":
        d = np.array([0.22, 0.22, 0.23], np.float32) * (1 + 0.03 * cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), 1.0))[..., None]
    elif kind == "white":
        d = np.array([0.72, 0.72, 0.69], np.float32) * (1 + 0.02 * cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), 1.0))[..., None]
    elif kind == "cluttered":
        d = np.array([0.42, 0.34, 0.26], np.float32) * grain(0.12)[..., None]
        d = np.ascontiguousarray(d)
        gx0, gy0, gx1, gy1 = (GC[0] - GW / 2) * P, (GC[1] - GH / 2) * P, (GC[0] + GW / 2) * P, (GC[1] + GH / 2) * P
        for _ in range(14):
            kind_o = rng.choice(["book", "sheet", "pen", "mug", "phone"])
            for _try in range(30):
                cx, cy = rng.uniform(0, w), rng.uniform(0, h)
                if not (gx0 - 30 < cx < gx1 + 30 and gy0 - 30 < cy < gy1 + 30):
                    break
            ang = rng.uniform(0, 180)
            if kind_o == "book":
                size, col = (rng.uniform(150, 300), rng.uniform(200, 400)), rng.uniform(0.05, 0.6, 3)
            elif kind_o == "sheet":
                size, col = (420 * 0.7, 594 * 0.7), np.array([0.8, 0.8, 0.78])
            elif kind_o == "pen":
                size, col = (16, 280), rng.uniform(0.02, 0.5, 3)
            elif kind_o == "phone":
                size, col = (140, 290), np.array([0.03, 0.03, 0.035])
            else:
                cv2.circle(d, (int(cx), int(cy)), 85, rng.uniform(0.1, 0.7, 3).tolist(), -1, cv2.LINE_AA)
                continue
            box = cv2.boxPoints(((cx, cy), size, ang)).astype(np.int32)
            cv2.fillPoly(d, [box], np.asarray(col, np.float32).tolist(), cv2.LINE_AA)
        # a pen half inside the ring, its tip reaching the guide
        cv2.line(d, (int(gx1 + 60), int(gy0 + 200)), (int(gx1 - 30), int(gy0 + 320)), (0.05, 0.05, 0.3), 16, cv2.LINE_AA)
    else:
        raise ValueError(kind)
    return np.ascontiguousarray(d, dtype=np.float32)


SKIN = [(0.55, 0.36, 0.28), (0.45, 0.30, 0.22), (0.30, 0.19, 0.13), (0.62, 0.45, 0.38)]


def hand_mask(x, y, a):
    """A right hand, palm centre (x, y) mm, fingers pointing away from the reader, the arm to the near edge;
    rotated by a degrees. Float mask on the plane."""
    m = np.zeros((PH, PW), np.uint8)
    up = np.array([math.sin(math.radians(a)), -math.cos(math.radians(a))])
    side = np.array([-up[1], up[0]])
    c = np.array([x, y])
    def pt(v):
        return tuple(int(round(t * P * 8)) for t in v)
    sh = 3  # fixed point
    cv2.ellipse(m, pt(c), (int(42 * P * 8), int(50 * P * 8)), a, 0, 360, 255, -1, cv2.LINE_AA, sh)
    for k, (off, ln) in enumerate([(-30, 70), (-10, 82), (10, 78), (29, 62)]):
        base = c + up * 38 + side * off
        tip = base + up * ln
        cv2.line(m, pt(base), pt(tip), 255, int(18 * P), cv2.LINE_AA, sh)
        cv2.circle(m, pt(tip), int(9 * P * 8), 255, -1, cv2.LINE_AA, sh)
    thumb0, thumb1 = c - side * 35, c - side * 75 + up * 30
    cv2.line(m, pt(thumb0), pt(thumb1), 255, int(22 * P), cv2.LINE_AA, sh)
    arm1 = c - up * 600
    cv2.line(m, pt(c), pt(arm1), 255, int(75 * P), cv2.LINE_AA, sh)
    return cv2.GaussianBlur(m, (0, 0), 1.5).astype(np.float32) / 255


# ---- the user's script --------------------------------------------------------------------------------------

class Script:
    """Builds the session tick by tick: which pages lie where, where the hand is, head bursts."""

    def __init__(self, rng):
        self.rng = rng
        self.desk = []      # [inst, page, cx, cy, th]
        self.carry = None   # [inst, page, dx, dy, th] relative to the hand
        self.hand = None    # [x, y, a]
        self.ticks = []
        self.instances = []
        self.off = (GC[0] + 230, GC[1] + GH / 2 + 330)

    def emit(self, n=1):
        for _ in range(n):
            self.ticks.append(dict(desk=[list(p) for p in self.desk], carry=list(self.carry) if self.carry else None,
                                   hand=list(self.hand) if self.hand else None))

    def idle(self, s):
        self.emit(int(round(s / DT)))

    def move(self, to, s, a=None, wobble=1.0):
        start = list(self.hand) if self.hand else [self.off[0], self.off[1], 20.0]
        a0 = start[2]
        a1 = a if a is not None else a0
        n = max(1, int(round(s / DT)))
        for i in range(1, n + 1):
            k = i / n
            e = k * k * (3 - 2 * k)
            w = wobble * (1 - e) * 3
            self.hand = [start[0] + (to[0] - start[0]) * e + self.rng.normal(0, w),
                         start[1] + (to[1] - start[1]) * e + self.rng.normal(0, w), a0 + (a1 - a0) * e]
            self.emit()

    def leave(self, s=0.6):
        self.move(self.off, s)
        self.hand = None

    def tremble(self, s, sd=1.2):
        x, y, a = self.hand
        for _ in range(int(round(s / DT))):
            self.hand = [x + self.rng.normal(0, sd), y + self.rng.normal(0, sd), a]
            self.emit()
        self.hand = [x, y, a]

    GRIP = (60.0, 125.0)  # the hand holds a page here, from its centre

    def bring(self, page, inst, misalign):
        dx, dy, th = misalign
        tx, ty = GC[0] + dx, GC[1] + dy
        self.hand = [self.off[0], self.off[1], 25.0]
        self.carry = [inst, page, -self.GRIP[0], -self.GRIP[1], th + self.rng.uniform(-8, 8)]
        self.move((tx + self.GRIP[0], ty + self.GRIP[1] + 40), 0.8, a=15)
        self.carry[4] = th
        self.move((tx + self.GRIP[0], ty + self.GRIP[1]), 0.4, a=12, wobble=0.5)
        self.desk.append([inst, page, tx, ty, th])
        self.carry = None
        self.instances.append(dict(inst=inst, page=page, t_place=len(self.ticks) * DT, misalign=misalign))

    def take_away(self):
        inst, page, cx, cy, th = self.desk.pop()
        self.desk.append([inst, page, cx, cy, th])
        self.move((cx + self.GRIP[0], cy + self.GRIP[1]), 0.6, a=12)
        self.desk.pop()
        self.carry = [inst, page, -self.GRIP[0], -self.GRIP[1], th]
        self.move((self.off[0] - 400, self.off[1]), 0.7, a=-10)
        self.carry = None
        self.hand = None


def build_script(seed):
    rng = np.random.default_rng(seed)
    s = Script(rng)
    order = rng.permutation(10)
    s.idle(2.0)
    # a hand passes over the empty guide
    s.move((GC[0] + 20, GC[1] + 40), 0.7)
    s.tremble(0.8, 3)
    s.leave()
    s.idle(1.5)
    for k, page in enumerate(order):
        mis = (0.0, 0.0, 0.0)
        r = rng.random()
        if r < 0.35:
            mis = (rng.uniform(-14, 14), rng.uniform(-18, 18), rng.uniform(-4, 4))
        elif r < 0.45:
            mis = (rng.choice([-1, 1]) * rng.uniform(18, 26), rng.uniform(-25, 25), rng.uniform(-3, 3))
        if k > 0:
            if rng.random() < 0.5:
                s.take_away()
                s.idle(rng.uniform(0.5, 1.5))
            # else: laid on top of the last one
        s.bring(int(page), k, mis)
        if rng.random() < 0.3:
            # the hand rests over the near edge before leaving
            s.move((GC[0] + 40 + mis[0], GC[1] + GH / 2 + 25 + mis[1]), 0.4)
            s.tremble(rng.uniform(1.2, 2.5))
        s.leave()
        s.idle(4.0)
        if rng.random() < 0.2:
            # the hand smooths the page and leaves: the same page, not a new one
            s.move((GC[0], GC[1] + 30), 0.6)
            s.tremble(0.8, 4)
            s.leave()
            s.idle(2.5)
    s.idle(2.0)
    return s


# ---- the camera ---------------------------------------------------------------------------------------------

def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def srgb_decode(x):
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


ENC_LUT = srgb_encode(np.arange(4096) / 4095.0).astype(np.float32)


def render_session(name):
    cv2.setNumThreads(2)
    c = cond(name)
    seed = sum(map(ord, name)) * 7919 + SEED
    rng = np.random.default_rng(seed)
    script = build_script(seed + 1)
    pg = pages()
    paper = np.array([0.86, 0.85, 0.82], np.float32) * rng.uniform(0.95, 1.02)
    inkc = rng.uniform(*c["ink"])
    refl = [paper[None, None, :] * (1 - inkc * (1 - p))[..., None] for p in pg]
    desk = make_desk(c["desk"], rng)
    skin = np.array(SKIN[rng.integers(len(SKIN))], np.float32)
    # light: colour, a gradient over the plane
    yy, xx = np.mgrid[0:PH, 0:PW].astype(np.float32)
    ang = rng.uniform(0, 2 * math.pi)
    grad = 1 + 0.15 * ((xx / PW - 0.5) * math.cos(ang) + (yy / PH - 0.5) * math.sin(ang)) * 2
    light = (np.array(c["light"], np.float32) / max(c["light"]))[None, None, :] * grad[..., None] * c["level"]
    shade = (skin[None, None, :] * (0.9 + 0.1 * np.sin(xx / 37 + yy / 53))[..., None]).astype(np.float32)
    shadow_dir = np.array([rng.uniform(-1, 1), rng.uniform(0.3, 1)]) * 22 * P
    # camera geometry
    k = rng.uniform(*c["scale"]) / P
    kf, cv = 0.82, 0.74
    wc, hc = int(PW * k) + 8, int(PH * k * cv) + 8
    src = np.float32([[0, 0], [PW, 0], [PW, PH], [0, PH]])
    dst = np.float32([[(1 - kf) / 2 * PW * k + 4, 4], [(1 + kf) / 2 * PW * k + 4, 4], [PW * k + 4, hc - 4], [4, hc - 4]])
    Hpc = cv2.getPerspectiveTransform(src, dst)
    # the sample grid: the guide plus the ring, the unit square, row 0 the near edge
    ex0, ex1 = (GC[0] - GW / 2 - RING_MM[0]) * P, (GC[0] + GW / 2 + RING_MM[0]) * P
    ey0, ey1 = (GC[1] - GH / 2 - RING_MM[1]) * P, (GC[1] + GH / 2 + RING_MM[1]) * P
    u = (np.arange(2 * FW) + 0.5) / (2 * FW)
    v = (np.arange(2 * FH) + 0.5) / (2 * FH)
    U, V = np.meshgrid(u, v)
    px = ex0 + U * (ex1 - ex0)
    py = ey1 - V * (ey1 - ey0)
    pts = cv2.perspectiveTransform(np.stack([px, py], -1).reshape(-1, 1, 2).astype(np.float64), Hpc).reshape(2 * FH, 2 * FW, 2)
    centre = pts.reshape(-1, 2).mean(0)
    offset = rng.normal(0, c["offset"], 2)
    awb = 1 + rng.normal(0, c["cast"], 3)
    awb /= awb.mean()
    gain = None
    ae_mult = 1.0
    burst_left = 0
    room = 0.12 * c["level"]
    samples = np.zeros((len(script.ticks), 2 * FH, 2 * FW, 3), np.uint8)
    top = np.full(len(script.ticks), -1, np.int32)
    cover = np.zeros(len(script.ticks), np.float32)
    handover = np.zeros(len(script.ticks), np.float32)
    gx0, gy0 = int((GC[0] - GW / 2) * P), int((GC[1] - GH / 2) * P)
    gx1, gy1 = gx0 + int(GW * P), gy0 + int(GH * P)
    blur_pre = max(0.0, 0.5 / k - 0.25)
    for i, tk in enumerate(script.ticks):
        t = i * DT
        img = desk.copy()
        topmask = None
        for inst, page, cx, cy, th in tk["desk"]:
            M = cv2.getRotationMatrix2D((GW * P / 2, GH * P / 2), th, 1.0)
            M[0, 2] += cx * P - GW * P / 2
            M[1, 2] += cy * P - GH * P / 2
            r = cv2.warpAffine(refl[page], M, (PW, PH), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0))
            mk = cv2.warpAffine(np.ones((int(GH * P), int(GW * P)), np.float32), M, (PW, PH), flags=cv2.INTER_LINEAR)
            img = img * (1 - mk[..., None]) + r
            topmask, top[i] = mk, inst
        if topmask is not None:
            cover[i] = topmask[gy0:gy1, gx0:gx1].mean()
        occl = np.zeros((PH, PW), np.float32)
        carried = None
        hm = None
        if tk["hand"]:
            hx, hy, ha = tk["hand"]
            hm = hand_mask(hx, hy, ha)
            occl = np.maximum(occl, hm)
            handover[i] = hm[gy0:gy1, gx0:gx1].mean()
            if tk["carry"]:
                inst, page, dx, dy, th = tk["carry"]
                M = cv2.getRotationMatrix2D((GW * P / 2, GH * P / 2), th, 1.0)
                M[0, 2] += (hx + dx) * P - GW * P / 2
                M[1, 2] += (hy + dy) * P - GH * P / 2
                r = cv2.warpAffine(refl[page], M, (PW, PH), flags=cv2.INTER_LINEAR)
                mk = cv2.warpAffine(np.ones((int(GH * P), int(GW * P)), np.float32), M, (PW, PH), flags=cv2.INTER_LINEAR)
                carried = (r, mk)
                occl = np.maximum(occl, mk)
                handover[i] = max(handover[i], mk[gy0:gy1, gx0:gx1].mean())
        if occl.any():
            Ms = np.float32([[1, 0, shadow_dir[0]], [0, 1, shadow_dir[1]]])
            small = cv2.resize(cv2.warpAffine(occl, Ms, (PW, PH)), (PW // 4, PH // 4), interpolation=cv2.INTER_AREA)
            sh = cv2.resize(cv2.GaussianBlur(small, (0, 0), 10 * P / 4), (PW, PH), interpolation=cv2.INTER_LINEAR)
            img = img * (1 - 0.45 * sh)[..., None]
            if carried:
                img = img * (1 - carried[1][..., None]) + carried[0]
            if hm is not None:
                img = img * (1 - hm[..., None]) + shade * hm[..., None]
        flick = 1 + c["flicker"] * math.sin(2 * math.pi * 1.7 * t + 0.3)
        irr = img * light * flick
        # camera: plane -> image crop
        if blur_pre > 0:
            irr = cv2.GaussianBlur(irr, (0, 0), blur_pre)
        cam = cv2.warpPerspective(irr, Hpc, (wc, hc), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        cam = cv2.GaussianBlur(cam, (0, 0), 0.7)
        if burst_left <= 0 and rng.random() < c["burst"]:
            burst_left = int(rng.integers(3, 7))
        jit = c["jitter"]
        if burst_left > 0:
            burst_left -= 1
            jit = 6.0
            L = int(rng.integers(5, 12))
            kern = np.zeros((L, L), np.float32)
            a = rng.uniform(0, math.pi)
            cv2.line(kern, (int(L / 2 - math.cos(a) * L / 2), int(L / 2 - math.sin(a) * L / 2)),
                     (int(L / 2 + math.cos(a) * L / 2), int(L / 2 + math.sin(a) * L / 2)), 1.0, 1)
            cam = cv2.filter2D(cam, -1, kern / max(kern.sum(), 1))
        lum = float((cam @ np.float32([0.2126, 0.7152, 0.0722])).mean())
        gt = np.clip(0.2 / (0.5 * room + 0.5 * lum + 1e-4), 0.3, c["gmax"])
        gain = gt if gain is None else gain + (gt - gain) * (1 - math.exp(-DT / 0.35))
        if c["ae_steps"] and rng.random() < c["ae_steps"]:
            ae_mult = rng.uniform(0.8, 1.25)
        ae_mult += (1.0 - ae_mult) * 0.03
        drift = 1 + 0.03 * math.sin(2 * math.pi * t / 23.0)
        lin = cam * (gain * ae_mult * drift) * awb[None, None, :].astype(np.float32)
        enc = ENC_LUT[(np.clip(lin, 0, 1) * 4095).astype(np.int32)]
        enc = c["black"] + (1 - c["black"]) * enc
        ycc = cv2.cvtColor(enc, cv2.COLOR_RGB2YCrCb)
        for ch in (1, 2):
            small = cv2.resize(ycc[..., ch], (wc // 2, hc // 2), interpolation=cv2.INTER_AREA)
            ycc[..., ch] = cv2.resize(small, (wc, hc), interpolation=cv2.INTER_LINEAR)
        n = c["noise"]
        ycc[..., 0] += rng.standard_normal((hc, wc), dtype=np.float32) * n * (0.5 + 0.5 * np.sqrt(np.clip(ycc[..., 0], 0, 1)))
        ycc[..., 1:] += rng.standard_normal((hc, wc, 2), dtype=np.float32) * (n * 0.5)
        enc = cv2.cvtColor(ycc, cv2.COLOR_YCrCb2RGB)
        enc8 = np.clip(np.round(enc * 255), 0, 255).astype(np.uint8)
        if c["readback"] == "linear":
            enc8 = np.clip(np.round(srgb_decode(enc8.astype(np.float32) / 255) * 255), 0, 255).astype(np.uint8)
        # the guide warp: one bilinear tap per output pixel, with the pose's registration error
        err = offset + rng.normal(0, jit, 2)
        rot = math.radians(rng.normal(0, 0.15))
        d = pts - centre
        mp = centre + err + np.stack([d[..., 0] * math.cos(rot) - d[..., 1] * math.sin(rot),
                                      d[..., 0] * math.sin(rot) + d[..., 1] * math.cos(rot)], -1)
        warped = cv2.remap(enc8, mp[..., 0].astype(np.float32), mp[..., 1].astype(np.float32), cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255)).astype(np.float32)
        samples[i] = np.round(warped).astype(np.uint8)  # the read-back, before any averaging
    os.makedirs(CACHE, exist_ok=True)
    inst = np.array([(d["inst"], d["page"], d["t_place"]) for d in script.instances], np.float32)
    np.savez_compressed(os.path.join(CACHE, name + ".npz"), samples=samples, top=top, cover=cover, handover=handover,
                        instances=inst)
    return name, len(script.ticks)


def load(name):
    z = np.load(os.path.join(CACHE, name + ".npz"))
    return {k: z[k] for k in z.files}


# ---- detectors ----------------------------------------------------------------------------------------------

def avg2(sample):
    """The read-back (2x) averaged 2x2, as ZumiScanner does it."""
    h, w = sample.shape[:2]
    return sample.reshape(h // 2, 2, w // 2, 2, -1).mean((1, 3))


def guide(sample, k=1):
    return sample[RY * k:(RY + SH) * k, RX * k:(RX + SW) * k]


class Baseline:
    """ZumiScanner as it stands: absolute paper luma/chroma share, block motion, ink share, re-arm."""
    name = "v0_baseline"
    uses_ring = False

    def __init__(self):
        self.armed = True
        self.hold = -1.0
        self.last = None

    def ready(self):
        self.hold = -1.0
        self.last = None

    def captured(self):
        self.armed = False
        self.hold = -1.0

    def feed(self, sample, t):
        g = guide(avg2(sample.astype(np.float32))) / 255
        r, gg, b = g[..., 0], g[..., 1], g[..., 2]
        l = 0.299 * r + 0.587 * gg + 0.114 * b
        chroma = g.max(-1) - g.min(-1)
        paper = (l >= 0.4) & (chroma <= 0.15)
        share = paper.mean()
        level = l[paper].mean() if paper.any() else 1.0
        dark = np.clip((level - l) / max(level, 0.05), 0, 1)
        ink = (dark >= 0.25).mean()
        blocks = block_mean(l, 16, 18)
        motion = 1.0 if self.last is None else float(np.abs(blocks - self.last).mean())
        self.last = blocks
        present = share >= 0.65
        still = motion <= 0.015
        if not self.armed and (not present or (0.06 <= motion < 1)):
            self.armed = True
        fresh = self.armed and ink >= 0.004
        self.dbg = dict(paper=share, motion=motion, ink=ink, armed=self.armed)
        if present and still and fresh:
            if self.hold < 0:
                self.hold = t
            if t - self.hold >= 0.6 - 1e-6:
                return "capture"
            return "holding"
        self.hold = -1.0
        return "seen" if present else "empty"


def block_mean(a, bx, by):
    h, w = a.shape
    ys = (np.arange(h) * by) // h
    xs = (np.arange(w) * bx) // w
    out = np.zeros((by, bx), np.float64)
    np.add.at(out, (ys[:, None], xs[None, :]), a)
    cnt = np.zeros((by, bx))
    np.add.at(cnt, (ys[:, None], xs[None, :]), 1)
    return out / cnt


class Relative:
    """Iterations 1 and 2 (kept to reproduce their rows), on the 2x2-averaged 64x90 sample.

    it1 paper relative to the guide's own white (its 90th-percentile colour), not to absolute luma and a neutral
        grey; the page must be brighter than the desk ring around the guide (or the desk is as light as paper).
    it2 + stillness on the exposure-normalised sample after the best whole-pixel shift, judged on the share of
        blocks whose mean absolute change is large; pencil by local contrast spread over blocks; armed by novelty
        (the pencil differs from the page taken last).
    """
    name = "relative"
    reg_still = False
    local_ink = False
    novelty_arm = False
    PAPER_REL, PAPER_CHROMA, PAPER_SHARE = 0.72, 0.16, 0.65
    PAGE_OVER_DESK, DESK_LIKE_PAPER, MIN_WHITE = 1.3, 0.8, 0.12
    STILL_BLOCK, STILL_SHARE, SHIFT = 0.04, 0.03, 2
    INK_REL, INK_SHARE, INK_BLOCKS = 0.82, 0.004, 8
    NOVEL, NOVEL_SHIFT = 0.35, 6
    HOLD = 0.6

    def __init__(self):
        self.armed = True
        self.hold = -1.0
        self.last = None
        self.sig_cap = None
        self.sig = None
        self.dbg = {}

    def ready(self):
        self.hold = -1.0
        self.last = None

    def captured(self):
        self.armed = False
        self.hold = -1.0
        self.sig_cap = self.sig

    def feed(self, sample, t):
        x = avg2(sample.astype(np.float32)) / 255
        L = x @ np.float32([0.299, 0.587, 0.114])
        G, Lg = guide(x), guide(L)
        thr = np.percentile(Lg, 90)
        wrgb = G[Lg >= thr].mean(0)
        W = float(wrgb @ np.float32([0.299, 0.587, 0.114]))
        Wsafe = max(W, 0.02)
        n = G / np.maximum(wrgb, 0.02)
        Ln = Lg / Wsafe
        rel_chroma = n.max(-1) - n.min(-1)
        paper = (Ln >= self.PAPER_REL) & (rel_chroma <= self.PAPER_CHROMA)
        share = float(paper.mean())
        ring = np.ones_like(L, bool)
        ring[RY:RY + SH, RX:RX + SW] = False
        desk = float(np.median(L[ring]))
        desk_light = desk >= self.DESK_LIKE_PAPER * W
        present = share >= self.PAPER_SHARE and W >= self.MIN_WHITE and (W >= self.PAGE_OVER_DESK * desk or desk_light)
        # motion
        Lnf = L / Wsafe
        if self.reg_still:
            motion, moved = self._registered_motion(Lnf)
            still = moved <= self.STILL_SHARE
        else:
            blocks = block_mean(Ln, 16, 18)
            motion = 1.0 if self.last is None else float(np.abs(blocks - self.last).mean())
            moved = motion
            self.last = blocks
            still = motion <= 0.015
        # pencil
        if self.local_ink:
            bg = cv2.blur(cv2.dilate(Ln, np.ones((3, 3), np.uint8)), (5, 5))
            dark = np.clip(1 - Ln / np.maximum(bg, 1e-3), 0, 1)
            inkpx = (Ln < self.INK_REL * bg) & (rel_chroma <= self.PAPER_CHROMA + 0.1)
            ink = float(inkpx.mean())
            inkblocks = int((block_mean(inkpx.astype(np.float32), 16, 18) > 0).sum())
            has_ink = ink >= self.INK_SHARE and inkblocks >= self.INK_BLOCKS
        else:
            dark = np.clip(1 - Ln, 0, 1)
            ink = float((dark >= 0.25).mean())
            inkblocks = -1
            has_ink = ink >= 0.004
        self.sig = cv2.GaussianBlur(dark.astype(np.float32), (0, 0), 1.0)
        hand, handed = 0.0, False
        # arming
        novelty = 1.0
        if self.novelty_arm:
            if self.sig_cap is not None:
                novelty = self._novelty(self.sig, self.sig_cap)
            if not self.armed and present and still and has_ink and not handed and novelty >= self.NOVEL:
                self.armed = True
        else:
            if not self.armed and (not present or (0.06 <= motion < 1)):
                self.armed = True
        self.dbg = dict(W=W, desk=desk, paper=share, motion=motion, moved=moved, ink=ink, blocks=inkblocks,
                        hand=hand, new=novelty, armed=self.armed)
        if present and still and has_ink and self.armed and not handed:
            if self.hold < 0:
                self.hold = t
            if t - self.hold >= self.HOLD - 1e-6:
                return "capture"
            return "holding"
        self.hold = -1.0
        return "seen" if present else "empty"

    def _registered_motion(self, Lnf):
        if self.last is None:
            self.last = Lnf
            return 1.0, 1.0
        best = None
        s = self.SHIFT
        cur = Lnf[RY:RY + SH, RX:RX + SW]
        for dy in range(-s, s + 1):
            for dx in range(-s, s + 1):
                prev = self.last[RY + dy:RY + dy + SH, RX + dx:RX + dx + SW]
                d = float(np.abs(cur - prev).mean())
                if best is None or d < best[0]:
                    best = (d, dx, dy)
        _, dx, dy = best
        prev = self.last[RY + dy:RY + dy + SH, RX + dx:RX + dx + SW]
        bd = block_mean(np.abs(cur - prev), 16, 18)
        self.last = Lnf
        return best[0], float((bd > self.STILL_BLOCK).mean())

    def _novelty(self, a, b):
        s = self.NOVEL_SHIFT
        tpl = b[s:-s, s:-s]
        if tpl.std() < 1e-4 or a.std() < 1e-4:
            return 1.0
        r = cv2.matchTemplate(a, tpl, cv2.TM_CCOEFF_NORMED)
        return float(1 - r.max())


class It1(Relative):
    name = "it1_relative_paper"


class It2(It1):
    name = "it2_still_ink_novelty"
    reg_still = True
    local_ink = True
    novelty_arm = True


LUMA = np.float32([0.299, 0.587, 0.114])


class PageDetector:
    """The final detector (iteration 5), ported to apps/xr/Assets/Zumi/Flow/ZumiPageDetector.cs.
    Input: the warp's read-back of the guide plus a desk ring, not averaged (2x: 192 x 268 RGB, sRGB bytes, row 0
    the near edge; the guide is cols 32..159, rows 44..223).

    1. White: the guide's 90th-percentile luma W (on the 2x2-averaged 96x134) and its colour. Every measure below
       is divided by W, so exposure, gain and most of the read-back's gamma drop out of the thresholds.
    2. Page: >= PAPER_SHARE of the guide is within PAPER_REL of W and within PAPER_CHROMA of W's colour (a cast
       light shifts paper and white together); and W >= PAGE_OVER_DESK x the desk ring's median, or, on a desk as
       light as the guide, W >= LIGHT_DESK_WHITE in absolute terms (an empty desk is its own white, but dimmer).
    3. Still: the previous normalised sample is aligned (best whole-pixel shift, then a least-squares fit of a
       sub-pixel shift, rotation, scale, gain and offset: head jitter and exposure); of the residual's 6x6-px blocks
       over the whole sample, ring included (an arm crosses it), at most STILL_BLOCKS changed their mean by more
       than max(STILL_BLOCK, STILL_NOISE x the median block change).
    4. Pencil: on the 2x read-back (averaging dilutes a 0.5 mm line into the paper), a pixel darker than the local
       paper (3x3 max, 5x5 box) by max(INK_DARK, INK_NOISE x the sample's own noise); max-pooled to 64x90; at least
       INK_SHARE of the guide, in at least INK_BLOCKS of 16x18 blocks.
    5. New: 1 - the best normalised correlation of the pencil map with each page taken (over shifts of
       +-NOVEL_SHIFT px) is >= NOVEL for all of them, on every held sample. A swap during the flight is taken; a
       hand smoothing the same page, or a page uncovered again by lifting the one on top, is not. forget() drops
       the last page (Undo).
    6. Capture: page, still, pencil and new for HOLD seconds.
    """
    name = "page_detector"
    PAPER_REL, PAPER_CHROMA, PAPER_SHARE = 0.72, 0.16, 0.65
    PAGE_OVER_DESK, DESK_LIKE_PAPER, MIN_WHITE = 1.3, 0.8, 0.12
    SHIFT, STILL_BLOCK, STILL_BLOCKS, BLOCK, STILL_NOISE = 2, 0.015, 3, 6, 4
    INK_DARK, INK_SHARE, INK_BLOCKS, INK_NOISE = 0.12, 0.004, 8, 5.0
    NOVEL, NOVEL_SHIFT = 0.5, 4
    HOLD = 0.6
    LIGHT_DESK_WHITE = 0.6
    full_still = True    # stillness over the ring too
    subpixel = True      # residual after a fitted sub-pixel shift, rotation, scale, gain and offset
    novel_all = True     # novelty against every page taken, checked on every held sample
    ink_noise = True     # pencil threshold at least INK_NOISE x the sample's noise
    light_desk_abs = True      # a guide no brighter than its desk must be bright in absolute terms (sRGB)

    def __init__(self):
        self.armed = True
        self.hold = -1.0
        self.last = None
        self.sig = None
        self.sig_cap = None
        self.sigs_cap = []
        self.dbg = {}

    def ready(self):
        self.hold = -1.0
        self.last = None

    def captured(self):
        self.armed = False
        self.hold = -1.0
        self.sig_cap = self.sig
        self.sigs_cap.append(self.sig)

    def forget(self):
        """The last page came off the stack (Undo): it may be taken again."""
        self.armed = True
        self.sig_cap = None
        if self.sigs_cap:
            self.sigs_cap.pop()

    def feed(self, sample, t):
        x2 = sample.astype(np.float32) / 255
        L2 = x2 @ LUMA
        x = avg2(x2)
        L = x @ LUMA
        G, Lg = guide(x), guide(L)
        W = float(np.percentile(Lg, 90))
        wrgb = G[Lg >= W].mean(0)
        Ws = max(W, 0.02)
        n = G / np.maximum(wrgb, 0.02)
        rel_chroma = n.max(-1) - n.min(-1)
        share = float(((Lg >= self.PAPER_REL * Ws) & (rel_chroma <= self.PAPER_CHROMA)).mean())
        ring = np.ones_like(L, bool)
        ring[RY:RY + SH, RX:RX + SW] = False
        desk = float(np.median(L[ring]))
        if self.light_desk_abs:
            # a guide no brighter than its desk: either an empty desk (its own white is the desk) or a page on a desk
            # as light as paper; only the latter is bright in absolute terms (paper is among the brightest things
            # the auto-exposure sees)
            lit = W >= self.PAGE_OVER_DESK * desk or W >= self.LIGHT_DESK_WHITE
        else:
            lit = W >= self.PAGE_OVER_DESK * desk or desk >= self.DESK_LIKE_PAPER * W
        present = share >= self.PAPER_SHARE and W >= self.MIN_WHITE and lit
        moved = self._moved(L / Ws)
        still = moved <= self.STILL_BLOCKS
        # pencil at the read-back's resolution
        Nf = L2 / Ws
        bgf = cv2.blur(cv2.dilate(Nf, np.ones((3, 3), np.uint8)), (5, 5), borderType=cv2.BORDER_REPLICATE)
        darkf = np.clip(1 - Nf / np.maximum(bgf, 1e-3), 0, 1)
        N2, dark2 = guide(Nf, 2), guide(darkf, 2)
        sig = dark2.reshape(SH, 2, SW, 2).max((1, 3))
        ink_thr = self.INK_DARK
        noise = 0.0
        if self.ink_noise:
            # the read-back's own noise, from neighbour differences (pencil is too sparse to move a median)
            noise = 1.4826 * float(np.median(np.abs(np.diff(N2, axis=1)))) / math.sqrt(2)
            ink_thr = max(self.INK_DARK, self.INK_NOISE * noise)
        inkpx = sig >= ink_thr
        ink = float(inkpx.mean())
        inkblocks = int((block_mean(inkpx.astype(np.float32), 16, 18) > 0).sum())
        has_ink = ink >= self.INK_SHARE and inkblocks >= self.INK_BLOCKS
        self.sig = cv2.blur(sig, (3, 3), borderType=cv2.BORDER_REPLICATE)
        novelty = 1.0
        if self.novel_all:
            if self.sigs_cap:
                novelty = min(ncc_novelty(self.sig, c, self.NOVEL_SHIFT) for c in self.sigs_cap)
            fresh = novelty >= self.NOVEL
            self.armed = fresh
        else:
            if self.sig_cap is not None:
                novelty = ncc_novelty(self.sig, self.sig_cap, self.NOVEL_SHIFT)
            if not self.armed and present and still and has_ink and novelty >= self.NOVEL:
                self.armed = True
        self.dbg = dict(W=W, desk=desk, paper=share, moved=moved, ink=ink, blocks=inkblocks, noise=noise,
                        new=novelty, armed=self.armed)
        if present and still and has_ink and self.armed:
            if self.hold < 0:
                self.hold = t
            if t - self.hold >= self.HOLD - 1e-6:
                return "capture"
            return "holding"
        self.hold = -1.0
        return "seen" if present else "empty"

    def _moved(self, N):
        prev, self.last = self.last, N
        if prev is None:
            return 999
        s = self.SHIFT
        h, w = N.shape
        cur = N[s:h - s, s:w - s]
        best = None
        for dy in range(-s, s + 1):
            for dx in range(-s, s + 1):
                p = prev[s + dy:h - s + dy, s + dx:w - s + dx]
                d = float(np.abs(cur - p).mean())
                if best is None or d < best[0]:
                    best = (d, p)
        p = best[1]
        if self.subpixel:
            cur = cur - lk_residual_fit(cur, p)
            p = np.zeros_like(p)
        if not self.full_still:
            cur = cur[RY - s:RY - s + SH, RX - s:RX - s + SW]
            p = p[RY - s:RY - s + SH, RX - s:RX - s + SW]
        hh, ww = cur.shape
        bd = np.abs(block_mean(cur, ww // self.BLOCK, hh // self.BLOCK) - block_mean(p, ww // self.BLOCK, hh // self.BLOCK))
        self.dbg_move = bd
        thr = max(self.STILL_BLOCK, self.STILL_NOISE * float(np.median(bd))) if self.STILL_NOISE else self.STILL_BLOCK
        return int((bd > thr).sum())


def lk_basis(p):
    """The ways the last sample can change without anything moving on the desk: a sub-pixel shift, a small
    rotation and scale about the centre (head jitter, pose timing), and an exposure gain and offset."""
    gy, gx = np.gradient(p)
    h, w = p.shape
    yc, xc = np.mgrid[0:h, 0:w].astype(np.float32)
    yc -= (h - 1) / 2
    xc -= (w - 1) / 2
    return np.stack([gx, gy, -gx * yc + gy * xc, gx * xc + gy * yc, p, np.ones_like(p)], -1).reshape(-1, 6)


def lk_residual_fit(cur, p):
    """cur - p explained by the basis (least squares); returns the explained part plus p, so cur minus it is
    what changed on the desk."""
    J = lk_basis(p).astype(np.float64)
    diff = (cur - p).reshape(-1).astype(np.float64)
    A = J.T @ J + np.eye(6) * 1e-6
    coef = np.linalg.solve(A, J.T @ diff)
    return (p.reshape(-1) + J @ coef).reshape(p.shape).astype(np.float32)


def ncc_novelty(a, b, s):
    """1 - the best normalised correlation of b's centre over a, shifted by up to s px."""
    tpl = b[s:-s, s:-s]
    if tpl.std() < 1e-4 or a.std() < 1e-4:
        return 1.0
    return float(1 - cv2.matchTemplate(a, tpl, cv2.TM_CCOEFF_NORMED).max())


class It4(PageDetector):
    """it3 + stillness over the ring too, on the residual after the fitted sub-pixel shift/rotation/scale/gain."""
    name = "it4_subpixel_still"
    novel_all = False
    ink_noise = False
    light_desk_abs = False
    NOVEL = 0.35


class It3(It4):
    """Pencil on the 2x read-back; stillness on block means (not mean absolute pixel change), guide only."""
    name = "it3_2x_ink_blockmean_still"
    full_still = False
    subpixel = False
    SHIFT, STILL_BLOCK, STILL_BLOCKS, BLOCK, STILL_NOISE = 2, 0.02, 1, 4, 0


class It5(PageDetector):
    """it4 + novelty against every page taken, on every held sample; pencil threshold over the sample's own noise;
    a guide no brighter than its desk must be bright in absolute terms."""
    name = "it5_final"


DETECTORS = {d.name: d for d in (Baseline, It1, It2, It3, It4, It5)}


# ---- scoring ------------------------------------------------------------------------------------------------

HAND_OVER = 0.004  # share of the guide under the hand (or a carried page) that counts as "a hand is there"
MIN_COVER = 0.80


def run(det_cls, name, blind=BLIND):
    s = load(name)
    det = det_cls()
    n = len(s["top"])
    caps = []
    trace = []
    resume = -1.0
    for i in range(n):
        t = i * DT
        if t < resume:
            trace.append("blind")
            continue
        if resume > 0:
            det.ready()
            resume = -1.0
        st = det.feed(s["samples"][i], t)
        trace.append(st)
        if st == "capture":
            caps.append(i)
            det.captured()
            resume = t + blind
    return score(s, caps), trace, caps


def score(s, caps):
    top, cover, hand = s["top"], s["cover"], s["handover"]
    n = len(top)
    # when each placement's hand left the guide, and its windows
    insts = s["instances"]
    left = {}
    for i in range(n):
        if top[i] >= 0 and hand[i] < HAND_OVER and top[i] not in left and cover[i] >= MIN_COVER:
            left[int(top[i])] = i * DT
    got = {}
    res = dict(ok=0, missed=0, double=0, false_hand=0, false_empty=0, lat=[])
    for i in caps:
        t = i * DT
        inst = int(top[i])
        if hand[i] >= HAND_OVER:
            res["false_hand"] += 1
            if inst >= 0:
                got.setdefault(inst, []).append(("hand", t))
        elif inst < 0 or cover[i] < 0.5:
            res["false_empty"] += 1
        elif inst in got and any(k == "ok" for k, _ in got[inst]):
            res["double"] += 1
        else:
            got.setdefault(inst, []).append(("ok", t))
            res["ok"] += 1
            res["lat"].append(t - left.get(inst, t))
    for d in insts:
        inst = int(d[0])
        if not any(k == "ok" for k, _ in got.get(inst, [])):
            res["missed"] += 1
    return res


def _run_score(dn, cn):
    return run(DETECTORS[dn], cn)[0]


def evaluate(names):
    conds = list(CONDITIONS)
    rows = []
    for dn in names:
        tot = dict(ok=0, missed=0, double=0, false_hand=0, false_empty=0, lat=[])
        print(f"\n== {dn}")
        print(f"{'condition':18s} {'ok':>3s} {'miss':>4s} {'dbl':>3s} {'fHand':>5s} {'fEmpty':>6s} {'lat med':>7s} {'lat max':>7s}")
        with Pool(len(conds)) as pool:
            results = pool.starmap(_run_score, [(dn, cn) for cn in conds])
        for cn, r in zip(conds, results):
            for k in tot:
                tot[k] = tot[k] + r[k]
            lat = r["lat"]
            print(f"{cn:18s} {r['ok']:3d} {r['missed']:4d} {r['double']:3d} {r['false_hand']:5d} {r['false_empty']:6d} "
                  f"{(np.median(lat) if lat else float('nan')):7.2f} {(max(lat) if lat else float('nan')):7.2f}")
        lat = tot["lat"]
        print(f"{'TOTAL':18s} {tot['ok']:3d} {tot['missed']:4d} {tot['double']:3d} {tot['false_hand']:5d} {tot['false_empty']:6d} "
              f"{(np.median(lat) if lat else float('nan')):7.2f} {(max(lat) if lat else float('nan')):7.2f}")
        rows.append((dn, tot))
    return rows


def explain(det_name, name, t0=0.0, t1=1e9):
    """Per sample: ground truth and the detector's state and measures, to read the failures."""
    s = load(name)
    r, _, _ = run(DETECTORS[det_name], name)
    det = DETECTORS[det_name]()
    resume = -1.0
    for i in range(len(s["top"])):
        t = i * DT
        if t < resume:
            continue
        if resume > 0:
            det.ready()
            resume = -1.0
        st = det.feed(s["samples"][i], t)
        if st == "capture":
            det.captured()
            resume = t + BLIND
        if t0 <= t <= t1:
            d = " ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in getattr(det, "dbg", {}).items())
            print(f"{t:6.1f} top={s['top'][i]:2d} cov={s['cover'][i]:.2f} hand={s['handover'][i]:.3f} {st:8s} {d}")
    print(r)


def replay(path, det_name="it5_final"):
    """Runs a detector over a headset recording: frames of [float32 time][192*268*4 RGBA bytes], as the scanner's
    read-back delivers them (see ZumiPageDetector.cs). Prints every state change and the measures."""
    rec = 4 + 2 * FW * 2 * FH * 4
    raw = np.fromfile(path, np.uint8)
    n = len(raw) // rec
    det = DETECTORS[det_name]()
    last = None
    resume = -1.0
    for i in range(n):
        b = raw[i * rec:(i + 1) * rec]
        t = float(b[:4].view(np.float32)[0])
        if t < resume:
            continue
        if resume > 0:
            det.ready()
            resume = -1.0
        img = b[4:].reshape(2 * FH, 2 * FW, 4)[..., :3]
        st = det.feed(img, t)
        if st != last or st == "capture":
            d = " ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in det.dbg.items())
            print(f"{t:8.2f} {st:8s} {d}")
            last = st
        if st == "capture":
            det.captured()
            resume = t + BLIND


def sheet(name, t0=0.0, n=40, step=1, out=None):
    s = load(name)
    i0 = int(t0 / DT)
    tiles = []
    for i in range(i0, min(i0 + n * step, len(s["top"])), step):
        im = s["samples"][i][..., ::-1].copy()
        im = np.ascontiguousarray(im[::-1])  # far edge up
        cv2.rectangle(im, (RX * 2, RY * 2), ((RX + SW) * 2, (RY + SH) * 2), (0, 255, 255), 1)
        cv2.putText(im, f"{i * DT:.1f} p{s['top'][i]} h{s['handover'][i]:.2f}", (2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
        tiles.append(im)
    while len(tiles) % 10:
        tiles.append(np.zeros_like(tiles[0]))
    grid = np.vstack([np.hstack(tiles[r:r + 10]) for r in range(0, len(tiles), 10)])
    out = out or os.path.join(CACHE, f"sheet_{name}_{t0:.0f}.png")
    cv2.imwrite(out, grid)
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "eval"
    if cmd == "render":
        names = sys.argv[2:] or list(CONDITIONS)
        with Pool(min(len(names), 4)) as pool:  # about 1 GB each
            for nm, nt in pool.imap_unordered(render_session, names):
                print("rendered", nm, nt, "samples")
    elif cmd == "eval":
        evaluate(sys.argv[2:] or list(DETECTORS))
    elif cmd == "replay":
        replay(*sys.argv[2:4])
    elif cmd == "explain":
        explain(sys.argv[2], sys.argv[3], *(float(a) for a in sys.argv[4:6]))
    elif cmd == "sheet":
        print(sheet(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0.0))
