"""Full-screen 16:9 "walkthrough" video: smooth camera moves over each photo,
push-through transitions, a real tour clip, and a branded end card.

Usage: python3 tour.py <scratch_dir> <photos_dir> <clip.mp4> <out.mp4> [still_times]
"""
import math, os, subprocess, sys
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SCR, PHOTOS, CLIP, OUT = sys.argv[1:5]
W, H, FPS = 1920, 1080, 30
XF = 0.8  # transition length (s)
FONT = {w: f"{SCR}/fonts/Rubik-{w}.ttf" for w in (500, 800, 900)}


def smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def ease_out(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def lerp(a, b, k):
    return a + (b - a) * k


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------------- camera over a still photo ----------------
class PhotoShot:
    """Camera = (cx, cy, zoom) in normalised image coords. zoom 1 = largest 16:9 view."""

    def __init__(self, path, dur, start, end, sway_seed=0):
        img = cv2.imread(path)
        # upscale once with high quality so per-frame resampling is mostly downscaling
        ih, iw = img.shape[:2]
        need = max(W / iw, H / ih) * 1.6
        if need > 1:
            img = cv2.resize(img, None, fx=need, fy=need, interpolation=cv2.INTER_LANCZOS4)
            blur = cv2.GaussianBlur(img, (0, 0), 1.2 * need)
            img = cv2.addWeighted(img, 1.35, blur, -0.35, 0)
        self.img = img
        self.dur, self.start, self.end = dur, start, end
        self.seed = sway_seed

    def frame(self, t, extra_zoom=1.0):
        ih, iw = self.img.shape[:2]
        k = smooth(t / self.dur)
        cx = lerp(self.start[0], self.end[0], k)
        cy = lerp(self.start[1], self.end[1], k)
        z = lerp(self.start[2], self.end[2], k) * extra_zoom
        # base 16:9 view that fits in the image
        bw = min(iw, ih * W / H)
        vw = bw / z; vh = vw * H / W
        # gentle "steady-cam" float
        s = self.seed
        dx = 0.006 * vw * math.sin(t * 0.9 + s)
        dy = 0.005 * vh * math.sin(t * 0.7 + 2 * s)
        ang = 0.25 * math.sin(t * 0.6 + s)
        x = cx * iw + dx; y = cy * ih + dy
        # keep the view (incl. rotation slack) inside the photo
        mx = vw / 2 * 1.01; my = vh / 2 * 1.01
        x = min(max(x, mx), iw - mx); y = min(max(y, my), ih - my)
        sc = W / vw
        M = cv2.getRotationMatrix2D((x, y), ang, sc)
        M[0, 2] += W / 2 - x; M[1, 2] += H / 2 - y
        return cv2.warpAffine(self.img, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


# ---------------- real tour footage ----------------
class ClipShot:
    def __init__(self, path, start, dur, zoom=(1.0, 1.06)):
        self.dur, self.zoom = dur, zoom
        raw = f"{SCR}/out/tourclip.rgb"
        vf = ("hqdn3d=2:1.5:6:4,crop=iw:iw*9/16:0:(ih-iw*9/16)*0.55,"
              f"scale={W}:{H}:flags=lanczos,unsharp=5:5:0.8:3:3:0,eq=saturation=1.12:contrast=1.04")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-t", str(dur + 0.2), "-i", path,
                        "-vf", vf, "-r", str(FPS), "-f", "rawvideo", "-pix_fmt", "bgr24", raw], check=True)
        n = os.path.getsize(raw) // (W * H * 3)
        self.frames = np.memmap(raw, np.uint8, "r", shape=(n, H, W, 3))

    def frame(self, t, extra_zoom=1.0):
        f = np.asarray(self.frames[min(len(self.frames) - 1, int(t * FPS))])
        z = lerp(self.zoom[0], self.zoom[1], smooth(t / self.dur)) * extra_zoom
        if abs(z - 1) < 1e-3:
            return f.copy()
        M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, z)
        return cv2.warpAffine(f, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


# ---------------- end card ----------------
def font(w, size):
    return ImageFont.truetype(FONT[w], size)


def text_img(txt, wt, size, col, shadow=True):
    f = font(wt, size)
    w = int(f.getlength(txt, direction="rtl")) + 80; h = int(size * 1.5)
    lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((w / 2, h / 2 + 4), txt, font=f, fill=(0, 0, 0, 150), anchor="mm", direction="rtl")
        lay = Image.alpha_composite(lay, sh.filter(ImageFilter.GaussianBlur(8)))
    ImageDraw.Draw(lay).text((w / 2, h / 2), txt, font=f, fill=col, anchor="mm", direction="rtl")
    return lay


def fade(im, a):
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    return im


class EndCard:
    def __init__(self, dur, bg_photo):
        self.dur = dur
        bg = cv2.imread(bg_photo)
        bg = cv2.resize(bg, (W // 6, int(W // 6 * bg.shape[0] / bg.shape[1])))
        bg = cv2.GaussianBlur(bg, (0, 0), 6)
        bg = cv2.resize(bg, (W, int(W * bg.shape[0] / bg.shape[1])))
        y0 = (bg.shape[0] - H) // 2
        bg = cv2.cvtColor(bg[y0:y0 + H], cv2.COLOR_BGR2RGB)
        tint = np.array(hexrgb("#0B2A55"), np.float32)
        self.bg = (bg.astype(np.float32) * 0.35 + tint * 0.65).astype(np.uint8)
        white = (255, 255, 255, 255)
        self.items = [
            (text_img("חידושים", 900, 150, white), 210, 0.2),
            (text_img("סביבות למידה חדשניות למוסדות חינוך", 500, 62, (215, 232, 245, 255)), 380, 0.45),
            (text_img("ליווי מקצה לקצה  •  הכל תחת מטריה אחת  •  מאושרים בתוכנית גפ\"ן", 800, 54, white), 520, 0.8),
        ]
        cta = text_img("רוצים כזה גם אצלכם? צרו קשר עוד היום", 900, 66, hexrgb("#0B2A55") + (255,), shadow=False)
        pw, ph = cta.width + 80, 136
        pill = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        ImageDraw.Draw(pill).rounded_rectangle((0, 0, pw - 1, ph - 1), ph // 2, fill=hexrgb("#FFD23F") + (255,))
        pill.alpha_composite(cta, ((pw - cta.width) // 2, (ph - cta.height) // 2 + 3))
        self.items.append((pill, 690, 1.2))

    def frame(self, t, extra_zoom=1.0):
        f = Image.fromarray(self.bg).convert("RGBA")
        for im, y, d0 in self.items:
            a = ease_out((t - d0) / 0.7)
            if a > 0:
                f.alpha_composite(fade(im, a), ((W - im.width) // 2, y + int(40 * (1 - a))))
        return cv2.cvtColor(np.asarray(f.convert("RGB")), cv2.COLOR_RGB2BGR)


# ---------------- timeline ----------------
def build():
    P = lambda i: f"{PHOTOS}/{i}.jpg"
    return [
        # wide establishing move along the sports stalls (right -> left, Hebrew reading direction)
        PhotoShot(P(2), 5.5, (0.70, 0.50, 1.35), (0.30, 0.50, 1.40), 1),
        # walk up to the ocean cubicles
        PhotoShot(P(1), 5.0, (0.50, 0.50, 1.00), (0.52, 0.42, 1.30), 2),
        # tilt down the wrapped entrance door
        PhotoShot(P(3), 5.5, (0.52, 0.22, 1.15), (0.50, 0.80, 1.22), 3),
        # drift across the starry stalls
        PhotoShot(P(4), 5.0, (0.42, 0.48, 1.08), (0.58, 0.50, 1.20), 4),
        # real walkthrough footage
        ClipShot(CLIP, 0.8, 9.0),
        EndCard(5.0, P(1)),
    ]


def main():
    shots = build()
    starts, t = [], 0.0
    for i, s in enumerate(shots):
        starts.append(t)
        t += s.dur - (XF if i < len(shots) - 1 else 0)
    total = t
    print(f"total {total:.2f}s", flush=True)

    def render(T):
        act = [(s, T - st, i) for i, (s, st) in enumerate(zip(shots, starts)) if st <= T < st + s.dur]
        if not act:
            act = [(shots[-1], shots[-1].dur - 1e-3, len(shots) - 1)]
        if len(act) == 1:
            s, lt, _ = act[0]
            return s.frame(lt)
        (a, la, _), (b, lb, _) = act[0], act[1]
        k = lb / XF  # 0..1 through the transition
        # push-through: outgoing keeps moving forward, incoming arrives from slightly "behind"
        za = 1 + 0.12 * k ** 2
        zb = 1.10 - 0.10 * ease_out(k)
        fa = a.frame(la, za); fb = b.frame(lb, zb)
        # light motion blur while moving between spaces
        if 0.15 < k < 0.85:
            fa = cv2.addWeighted(fa, 0.5, a.frame(la, za * 1.012), 0.5, 0)
        m = smooth(k)
        return cv2.addWeighted(fa, 1 - m, fb, m, 0)

    if len(sys.argv) > 5:
        for T in map(float, sys.argv[5].split(",")):
            cv2.imwrite(f"{SCR}/out/tour_{T:05.1f}.jpg", render(T), [cv2.IMWRITE_JPEG_QUALITY, 88])
        return

    wav = f"{SCR}/out/tour_music.wav"
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "music.py"), f"{total:.3f}", wav], check=True)
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                           OUT], stdin=subprocess.PIPE)
    n = int(round(total * FPS))
    for i in range(n):
        ff.stdin.write(render(i / FPS).tobytes())
        if i % 150 == 0:
            print(f"frame {i}/{n}", flush=True)
    ff.stdin.close(); ff.wait()
    print("done", OUT)


if __name__ == "__main__":
    main()
