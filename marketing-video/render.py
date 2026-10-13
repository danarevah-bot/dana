"""Render a vertical (1080x1920) marketing tour video from photos + clips.

Usage: python3 render.py <scratch_dir> <images_dir> <video1> <video2> <out.mp4>
"""
import math, os, subprocess, sys, json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

SCR, IMG, V1, V2, OUT = sys.argv[1:6]
W, H, FPS = 1080, 1920, 30
XF = 0.5  # crossfade seconds
FONT = {w: f"{SCR}/fonts/Rubik-{w}.ttf" for w in (500, 800, 900)}
CARD_CY = 960
CARD_MAX_W, CARD_MAX_H = 1020, 1500


def card_size(iw, ih):
    cw = CARD_MAX_W; ch = int(cw * ih / iw)
    if ch > CARD_MAX_H:
        ch = CARD_MAX_H; cw = int(ch * iw / ih)
    return cw, ch


def enhance(im):
    """Gentle clean-up for phone photos: levels, colour, contrast, crisp detail."""
    from PIL import ImageEnhance
    im = ImageOps.autocontrast(im, cutoff=0.4, preserve_tone=True)
    im = ImageEnhance.Color(im).enhance(1.15)
    im = ImageEnhance.Contrast(im).enhance(1.05)
    return im.filter(ImageFilter.UnsharpMask(radius=1.6, percent=70, threshold=3))


def font(w, size):
    return ImageFont.truetype(FONT[w], size)


def ease(x):
    x = min(1, max(0, x))
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = min(1, max(0, x))
    return 0.5 - 0.5 * math.cos(math.pi * x)


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------- text ----------
def text_layer(lines, width=W, pad=30):
    """lines: list of (text, weight, size, color). Returns RGBA image with soft shadow."""
    fitted = []
    for txt, wt, size, col in lines:
        f = font(wt, size)
        while f.getlength(txt, direction="rtl") > width - 2 * 70 and size > 20:
            size -= 2
            f = font(wt, size)
        fitted.append((txt, f, size, col))
    heights = [int(s * 1.25) for _, _, s, _ in fitted]
    h = sum(heights) + 2 * pad
    lay = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    sh = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay); ds = ImageDraw.Draw(sh)
    y = pad
    for (txt, f, s, col), lh in zip(fitted, heights):
        ds.text((width / 2, y + 4), txt, font=f, fill=(0, 0, 0, 200), anchor="ma", direction="rtl")
        d.text((width / 2, y), txt, font=f, fill=col, anchor="ma", direction="rtl")
        y += lh
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    return Image.alpha_composite(sh, lay)


def with_alpha(im, a):
    if a >= 0.999:
        return im
    im = im.copy()
    al = im.getchannel("A").point(lambda v: int(v * a))
    im.putalpha(al)
    return im


class Caption:
    def __init__(self, title, sub, accent, t0, t1, y=1430, tag=None):
        self.accent = hexrgb(accent)
        lines = []
        if tag:
            lines.append((tag, 800, 40, self.accent + (255,)))
        lines += [(title, 900, 92, (255, 255, 255, 255)), (sub, 500, 50, (235, 240, 248, 255))]
        self.img = text_layer(lines)
        self.t0, self.t1, self.y = t0, t1, y

    def draw(self, frame, t):
        if t < self.t0 or t > self.t1:
            return
        a_in = ease((t - self.t0) / 0.7)
        a_out = min(1, max(0, (self.t1 - t) / 0.35))
        a = a_in * a_out
        if a <= 0:
            return
        dy = int(50 * (1 - a_in))
        # accent bar grows from the right (RTL)
        bw = int(140 * ease((t - self.t0 - 0.15) / 0.6))
        if bw > 2:
            bar = Image.new("RGBA", (bw, 12), (0, 0, 0, 0))
            ImageDraw.Draw(bar).rounded_rectangle((0, 0, bw - 1, 11), 6, fill=self.accent + (int(255 * a),))
            frame.alpha_composite(bar, (W // 2 + 70 - bw, self.y - 6))
        frame.alpha_composite(with_alpha(self.img, a), (0, self.y + 14 + dy))


# ---------- visual helpers ----------
def cover(im, w, h):
    return ImageOps.fit(im, (w, h), Image.LANCZOS)


def blurred_bg(im, dark=0.42):
    small = cover(im, W // 8, H // 8).filter(ImageFilter.GaussianBlur(5))
    bg = small.resize((W, H), Image.BILINEAR).convert("RGB")
    arr = np.asarray(bg).astype(np.float32) * dark
    # darker toward the bottom for caption legibility
    arr *= np.concatenate([np.ones((H // 2, 1, 1)), np.linspace(1.0, 0.5, H - H // 2)[:, None, None]])
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8)).convert("RGBA")


_mask_cache = {}


def card_assets(cw, ch, r=40):
    key = (cw, ch)
    if key not in _mask_cache:
        m = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, cw - 1, ch - 1), r, fill=255)
        pad = 80
        s = Image.new("RGBA", (cw + 2 * pad, ch + 2 * pad), (0, 0, 0, 0))
        ImageDraw.Draw(s).rounded_rectangle((pad, pad + 24, pad + cw, pad + ch + 24), r, fill=(0, 0, 0, 170))
        s = s.filter(ImageFilter.GaussianBlur(28))
        border = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(border).rounded_rectangle((0, 0, cw - 1, ch - 1), r, outline=(255, 255, 255, 90), width=4)
        _mask_cache[key] = (m, s, pad, border)
    return _mask_cache[key]


def paste_card(frame, src, cw, ch, zoom, panx=0.0, pany=0.0, cy=CARD_CY, lift=0):
    """src: PIL image already sized ~ (cw, ch) aspect. zoom>=1 crops into it smoothly."""
    sw, sh = src.size
    sc = min(sw / cw, sh / ch) / zoom
    vis_w, vis_h = cw * sc, ch * sc
    x0 = (sw - vis_w) / 2 + panx * (sw - vis_w) / 2
    y0 = (sh - vis_h) / 2 + pany * (sh - vis_h) / 2
    card = src.transform((cw, ch), Image.AFFINE, (sc, 0, x0, 0, sc, y0), Image.BICUBIC).convert("RGBA")
    m, s, pad, border = card_assets(cw, ch)
    card.putalpha(m)
    x = (W - cw) // 2
    y = cy - ch // 2 - lift
    frame.alpha_composite(s, (x - pad, y - pad))
    frame.alpha_composite(card, (x, y))
    frame.alpha_composite(border, (x, y))


class Bubbles:
    def __init__(self, n, seed, colors):
        r = np.random.default_rng(seed)
        self.b = [dict(x=r.uniform(0, W), y=r.uniform(0, H), rad=r.uniform(14, 70), sp=r.uniform(40, 140),
                       wob=r.uniform(0, 6.28), col=colors[i % len(colors)], a=r.uniform(40, 110)) for i in range(n)]

    def draw(self, frame, t, alpha=1.0):
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        for b in self.b:
            y = (b["y"] - b["sp"] * t) % (H + 200) - 100
            x = b["x"] + 25 * math.sin(t * 1.3 + b["wob"])
            r = b["rad"]
            d.ellipse((x - r, y - r, x + r, y + r), fill=b["col"] + (int(b["a"] * alpha),))
        frame.alpha_composite(lay)


def gradient_bg(c1, c2, t=0.0):
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(0, 1, W)[None, :]
    k = np.clip(0.65 * y + 0.35 * x + 0.08 * math.sin(t * 0.9), 0, 1)[..., None]
    a = np.array(hexrgb(c1), np.float32); b = np.array(hexrgb(c2), np.float32)
    arr = a * (1 - k) + b * k
    return Image.fromarray(arr.astype(np.uint8)).convert("RGBA")


# ---------- sources ----------
def load_img(name):
    im = Image.open(f"{IMG}/{name}")
    return ImageOps.exif_transpose(im).convert("RGB")


def decode(path, key, scale=1.12):
    info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                               "stream=width,height,r_frame_rate", "-of", "json", path]))["streams"][0]
    num, den = map(int, info["r_frame_rate"].split("/"))
    probe = f"{SCR}/out/{key}_probe.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-frames:v", "1", probe], check=True)
    w, h = Image.open(probe).size  # dimensions after auto-rotation
    cw, ch = card_size(w, h)
    w, h = int(cw * scale) // 2 * 2, int(ch * scale) // 2 * 2
    # denoise, high-quality upscale to the on-screen size, then sharpen and lift colour
    vf = (f"hqdn3d=2:1.5:6:4,scale={w}:{h}:flags=lanczos,"
          "unsharp=5:5:0.9:3:3:0,eq=saturation=1.15:contrast=1.05")
    raw = f"{SCR}/out/{key}.rgb"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", raw],
                   check=True)
    n = os.path.getsize(raw) // (w * h * 3)
    return np.memmap(raw, np.uint8, "r", shape=(n, h, w, 3)), num / den


# ---------- segments ----------
class Intro:
    def __init__(self, dur, bgsrc):
        self.dur = dur
        self.bg = blurred_bg(bgsrc, 0.5)
        tint = gradient_bg("#0B2A55", "#0E7490")
        self.bg = Image.blend(self.bg, tint, 0.55)
        self.bub = Bubbles(22, 3, [(255, 255, 255), (79, 195, 247), (255, 210, 63)])
        self.l1 = text_layer([("הופכים את חדרי השירותים", 900, 88, (255, 255, 255, 255))])
        self.l2 = text_layer([("לחוויה צבעונית", 900, 140, hexrgb("#FFD23F") + (255,))])
        self.l3 = text_layer([("עיצוב והלבשת חללים במוסדות חינוך", 500, 54, (230, 240, 250, 255)),
                              ("מהרעיון ועד ההתקנה בשטח", 500, 54, (230, 240, 250, 255))])

    def frame(self, t):
        f = self.bg.copy()
        self.bub.draw(f, t)
        for lay, y, d0 in ((self.l1, 640, 0.15), (self.l2, 760, 0.45), (self.l3, 1010, 0.9)):
            a = ease((t - d0) / 0.7)
            if a > 0:
                f.alpha_composite(with_alpha(lay, a), (0, y + int(60 * (1 - a))))
        # underline swoosh
        a = ease((t - 0.8) / 0.6)
        if a > 0:
            bw = int(520 * a)
            ImageDraw.Draw(f).rounded_rectangle((W // 2 + 260 - bw, 965, W // 2 + 260, 979), 7, fill=hexrgb("#FF6B6B") + (255,))
        return f


class Photo:
    def __init__(self, im, dur, captions, zoom=(1.0, 1.12), pan=(0.0, 0.0, 0.0, 0.0)):
        self.dur, self.captions, self.zoom, self.pan = dur, captions, zoom, pan
        self.bg = blurred_bg(im)
        self.cw, self.ch = card_size(*im.size)
        self.src = im.resize((int(self.cw * 1.15), int(self.ch * 1.15)), Image.LANCZOS)  # photos are pre-retouched by fixphotos.py
        self.cy = CARD_CY

    def frame(self, t):
        k = ease_io(t / self.dur)
        f = self.bg.copy()
        z = self.zoom[0] + (self.zoom[1] - self.zoom[0]) * k
        px = self.pan[0] + (self.pan[1] - self.pan[0]) * k
        py = self.pan[2] + (self.pan[3] - self.pan[2]) * k
        paste_card(f, self.src, self.cw, self.ch, z, px, py, cy=self.cy)
        for c in self.captions:
            c.draw(f, t)
        return f


class Clip:
    def __init__(self, frames, fps, dur, captions, zoom=(1.0, 1.06)):
        self.frames, self.fps, self.dur, self.captions, self.zoom = frames, fps, dur, captions, zoom
        n, h, w, _ = frames.shape
        self.cw, self.ch = card_size(w, h)
        self.cy = CARD_CY

    def frame(self, t):
        i = min(len(self.frames) - 1, int(t * self.fps))
        im = Image.fromarray(np.asarray(self.frames[i]))
        f = blurred_bg(im, 0.4)
        z = self.zoom[0] + (self.zoom[1] - self.zoom[0]) * ease_io(t / self.dur)
        paste_card(f, im, self.cw, self.ch, z, cy=self.cy)
        for c in self.captions:
            c.draw(f, t)
        return f


class Outro:
    def __init__(self, dur, photos):
        self.dur = dur
        self.bub = Bubbles(18, 11, [(255, 255, 255), (255, 210, 63), (255, 107, 107)])
        tw, th = 470, 352
        self.tiles = []
        for p in photos:
            m, s, pad, border = card_assets(tw, th, 28)
            tile = cover(p, tw, th).convert("RGBA"); tile.putalpha(m)
            self.tiles.append((tile, s, pad, border))
        self.tw, self.th = tw, th
        self.title = text_layer([("רוצים כזה גם אצלכם?", 900, 96, (255, 255, 255, 255))])
        self.feats = [text_layer([(s, 800, 54, (255, 255, 255, 255))]) for s in
                      ("ליווי מקצה לקצה", "הכל תחת מטריה אחת", "מאושרים בתוכנית גפ\"ן")]
        self.cta = text_layer([("צרו קשר עוד היום", 900, 64, hexrgb("#0B2A55") + (255,))], pad=10)
        self.brand = text_layer([("חידושים", 900, 60, (255, 255, 255, 255)),
                                 ("סביבות למידה חדשניות למוסדות חינוך", 500, 36, (210, 230, 245, 255))], pad=0)
        self.dot_cols = ["#4FC3F7", "#FFD23F", "#FF6B6B"]

    def frame(self, t):
        f = gradient_bg("#0B2A55", "#0E7490", t)
        self.bub.draw(f, t, 0.8)
        gap = 24
        x0 = (W - 2 * self.tw - gap) // 2
        for i, (tile, s, pad, border) in enumerate(self.tiles):
            a = ease((t - 0.1 * i) / 0.6)
            if a <= 0:
                continue
            col, row = 1 - i % 2, i // 2  # RTL: first tile on the right
            x = x0 + col * (self.tw + gap)
            y = 150 + row * (self.th + gap) + int(40 * (1 - a))
            f.alpha_composite(with_alpha(s, a), (x - pad, y - pad))
            f.alpha_composite(with_alpha(tile, a), (x, y))
            f.alpha_composite(with_alpha(border, a), (x, y))
        a = ease((t - 0.5) / 0.6)
        if a > 0:
            f.alpha_composite(with_alpha(self.title, a), (0, 940 + int(40 * (1 - a))))
        d = ImageDraw.Draw(f)
        for i, lay in enumerate(self.feats):
            a = ease((t - 1.0 - 0.3 * i) / 0.5)
            if a <= 0:
                continue
            y = 1120 + i * 105
            f.alpha_composite(with_alpha(lay, a), (0, y + int(30 * (1 - a))))
        # CTA pill with a gentle pulse
        a = ease((t - 2.2) / 0.6)
        if a > 0:
            pulse = 1 + 0.03 * math.sin(max(0, t - 2.8) * 5)
            pw, ph = int(640 * pulse), int(130 * pulse)
            pill = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            ImageDraw.Draw(pill).rounded_rectangle((0, 0, pw - 1, ph - 1), ph // 2, fill=hexrgb("#FFD23F") + (255,))
            cta = self.cta.resize((int(self.cta.width * pulse), int(self.cta.height * pulse)), Image.LANCZOS)
            pill.alpha_composite(cta, ((pw - cta.width) // 2, (ph - cta.height) // 2 + 4))
            f.alpha_composite(with_alpha(pill, a), ((W - pw) // 2, 1480 - (ph - 130) // 2 + int(30 * (1 - a))))
        a = ease((t - 2.7) / 0.6)
        if a > 0:
            f.alpha_composite(with_alpha(self.brand, a), (0, 1660))
        return f


def main():
    p1, p2, p3, p4 = (load_img(f"{i}.jpg") for i in (1, 2, 3, 4))
    f1, fps1 = decode(V1, "v1")
    f2, fps2 = decode(V2, "v2")
    d1 = min(12.2, len(f1) / fps1)
    d2 = len(f2) / fps2 - 0.05

    segs = [
        Intro(3.6, p1),
        Photo(p4, 3.8, [],
              zoom=(1.02, 1.14), pan=(-0.4, 0.4, 0, 0)),
        Photo(p1, 3.8, [],
              zoom=(1.14, 1.02), pan=(0.3, -0.3, 0, 0)),
        Photo(p3, 3.8, [],
              zoom=(1.0, 1.10), pan=(0, 0, 0.5, -0.3)),
        Photo(p2, 3.8, [],
              zoom=(1.02, 1.12), pan=(0.4, -0.4, 0, 0)),
        Clip(f1, fps1, d1, []),
        Clip(f2, fps2, d2, []),
        Outro(6.5, [p1, p4, p2, p3]),
    ]
    starts, t = [], 0.0
    for i, s in enumerate(segs):
        starts.append(t)
        t += s.dur - (XF if i < len(segs) - 1 else 0)
    total = t
    print(f"total {total:.2f}s", flush=True)
    with open(f"{SCR}/out/duration.txt", "w") as fh:
        fh.write(f"{total:.3f}")

    if len(sys.argv) > 6:  # preview stills mode
        times = [float(x) for x in sys.argv[6].split(",")]
    else:
        times = None

    def render(T):
        active = [(s, T - st) for s, st in zip(segs, starts) if st <= T < st + s.dur]
        if not active:
            active = [(segs[-1], segs[-1].dur - 1 / FPS)]
        s, lt = active[0]
        img = s.frame(lt)
        if len(active) > 1:
            s2, lt2 = active[1]
            img = Image.blend(img, s2.frame(lt2), ease_io(lt2 / XF))
        return img.convert("RGB")

    if times:
        for T in times:
            render(T).save(f"{SCR}/out/still_{T:05.1f}.jpg", quality=85)
        return

    nframes = int(round(total * FPS))
    wav = f"{SCR}/out/music.wav"
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "music.py"), f"{total:.3f}", wav], check=True)
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "slow", "-crf", "16",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", OUT],
                          stdin=subprocess.PIPE)
    for n in range(nframes):
        ff.stdin.write(render(n / FPS).tobytes())
        if n % 150 == 0:
            print(f"frame {n}/{nframes}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("done", OUT)


if __name__ == "__main__":
    main()
