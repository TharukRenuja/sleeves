#!/usr/bin/env python3
"""Render the album wall. No flags: edit the constants below if you ever want to change it.

Reads ./covers, writes:
  dist/wall.jpg                 poster (first frame, 720p)
  dist/<res>/wall.webm          AV1
  dist/<res>/vp9/wall.webm      VP9 fallback
Needs: pillow, numpy, ffmpeg with libsvtav1 (or libaom-av1) and libvpx-vp9.
"""
import datetime, glob, math, os, random, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw

# ---- settings -------------------------------------------------------------
COVERS = "covers"
OUT = "dist"
SIZES = {"360p": (640, 360), "480p": (854, 480), "720p": (1280, 720), "1080p": (1920, 1080)}
POSTER_SIZE, POSTER_QUALITY = "720p", 65
ROWS, PER_ROW = 10, 8          # cards per row loop
SPEED = 0.5                    # cards per second (loop = PER_ROW / SPEED seconds)
FPS, GOP = 15, 240
AV1_CRF, AV1_PRESET = 52, 6
VP9_CRF = 46
CARD, GAP, RADIUS = 105, 0.10, 0.045   # card pitch px @1280w, gap and corner radius ratios
VIGNETTE = 0.45
BG = (12, 12, 14)
SEED = int(datetime.date.today().strftime("%Y%m%d"))   # daily shuffle
# ---------------------------------------------------------------------------
ASPECT = 1.72  # keeps cards square after the perspective warp


def load_covers(S):
    files = sorted(sum((glob.glob(f"{COVERS}/*.{e}") for e in ("jpg", "jpeg", "png", "webp")), []))
    if not files:
        sys.exit(f"no images in {COVERS}/ (run fetch.py first)")
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], max(1, int(S * RADIUS)), fill=255)
    out = []
    for f in files:
        im = Image.open(f).convert("RGB")
        w, h = im.size
        m = min(w, h)
        im = im.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m)).resize((S, S), Image.LANCZOS)
        card = Image.new("RGB", (S, S), BG)
        card.paste(im, (0, 0), mask)
        out.append(np.asarray(card))
    return out


def persp_coeffs(dst, src):
    A, B = [], []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    return tuple(np.linalg.solve(np.array(A, float), np.array(B, float)))


def encoders():
    have = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if "libsvtav1" in have:
        av1 = ["-c:v", "libsvtav1", "-crf", str(AV1_CRF), "-preset", str(AV1_PRESET), "-g", str(GOP)]
    elif "libaom-av1" in have:
        av1 = ["-c:v", "libaom-av1", "-crf", str(AV1_CRF), "-b:v", "0", "-cpu-used", "6", "-row-mt", "1", "-g", str(GOP)]
    else:
        sys.exit("ffmpeg has no AV1 encoder (need libsvtav1 or libaom-av1)")
    vp9 = ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(VP9_CRF), "-g", str(GOP), "-lag-in-frames", "25",
           "-auto-alt-ref", "1", "-row-mt", "1", "-deadline", "good", "-cpu-used", "2"]
    return av1, vp9


def ffmpeg_cmd(W, H, codec_args, out):
    return (["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
             "-framerate", str(FPS), "-i", "-", "-an"] + codec_args + ["-pix_fmt", "yuv420p", out])


def render(size, av1_args, vp9_args):
    W, H = SIZES[size]
    s = W / 1280
    P = max(8, round(CARD * s)); gap = max(2, round(P * GAP)); S = P - gap
    CH = ROWS * P; CW = int(CH * ASPECT); RP = PER_ROW * P
    covers = load_covers(S)

    seconds = PER_ROW / SPEED
    N = max(2, round(FPS * seconds))
    print(f"[{size}] {seconds:.0f}s loop, {N} frames")

    rng = random.Random(SEED)
    pool = []
    while len(pool) < ROWS * PER_ROW:
        c = covers[:]; rng.shuffle(c); pool += c

    reps = math.ceil(CW / RP) + 2
    rows = []
    for r in range(ROWS):
        tile = np.full((P, RP, 3), BG, np.uint8)
        for i in range(PER_ROW):
            x = i * P + gap // 2
            tile[gap // 2: gap // 2 + S, x: x + S] = pool[r * PER_ROW + i]
        rows.append(np.tile(tile, (1, reps, 1)))

    dst = [(-420 * s, -260 * s), (W + 330 * s, -60 * s), (W + 420 * s, H + 330 * s), (-520 * s, H + 60 * s)]
    co = persp_coeffs(dst, [(0, 0), (CW, 0), (CW, CH), (0, CH)])
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    vig = np.clip(1.1 - VIGNETTE * d ** 1.8, .3, 1).astype(np.float32)[..., None]

    d_av1 = os.path.join(OUT, size); d_vp9 = os.path.join(OUT, size, "vp9")
    os.makedirs(d_vp9, exist_ok=True)
    paths = [os.path.join(d_av1, "wall.webm"), os.path.join(d_vp9, "wall.webm")]
    procs = [subprocess.Popen(ffmpeg_cmd(W, H, av1_args, paths[0]), stdin=subprocess.PIPE),
             subprocess.Popen(ffmpeg_cmd(W, H, vp9_args, paths[1]), stdin=subprocess.PIPE)]

    canvas = np.empty((CH, CW, 3), np.uint8)
    for t in range(N):
        sh = t / N * RP
        for r in range(ROWS):
            sx = int(round(sh if r % 2 == 0 else -sh)) % RP     # even rows left, odd rows right
            canvas[r * P:(r + 1) * P] = rows[r][:, sx:sx + CW]
        fr = Image.fromarray(canvas).transform((W, H), Image.PERSPECTIVE, co, Image.BICUBIC)
        arr = (np.asarray(fr, np.float32) * vig).astype(np.uint8)
        if t == 0 and size == POSTER_SIZE:
            Image.fromarray(arr).save(os.path.join(OUT, "wall.jpg"), quality=POSTER_QUALITY,
                                      optimize=True, progressive=True)
        raw = arr.tobytes()
        for p in procs:
            p.stdin.write(raw)
    for p in procs:
        p.stdin.close()
    for p, path in zip(procs, paths):
        if p.wait() != 0:
            sys.exit(f"ffmpeg failed for {path}")
        print(f"  {path}: {os.path.getsize(path) / 1024:.0f} KB")


def main():
    av1_args, vp9_args = encoders()
    for size in SIZES:
        render(size, av1_args, vp9_args)
    poster = os.path.join(OUT, "wall.jpg")
    print(f"  {poster}: {os.path.getsize(poster) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
