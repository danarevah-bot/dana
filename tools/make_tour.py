import subprocess, sys, wave
import numpy as np
from PIL import Image, ImageFilter

IMG = sys.argv[1]
OUT = sys.argv[2]
W, H, FPS = 1920, 1080, 30
XF = 1.0  # crossfade seconds

src = {k: Image.open(f"{IMG}/{k}.jpg").convert("RGB") for k in (1, 2, 3)}

# (image, duration, start(cx,cy,w), end(cx,cy,w)) — camera window in source px
SHOTS = [
    (1, 5.5, (600, 780, 1150), (780, 800, 880)),     # door sign -> into the room
    (2, 7.5, (520, 600, 1050), (1060, 560, 980)),    # Edison stall -> Einstein quote
    (3, 7.5, (560, 570, 1000), (1120, 560, 1000)),   # quote/satellite -> Ada Yonath
    (2, 5.0, (800, 590, 1150), (800, 600, 1500)),    # wide pull-back
]


def ease(t):
    return t * t * t * (t * (6 * t - 15) + 10)  # smootherstep


def frame(img, cx, cy, w):
    h = w * H / W
    s = w / W
    return img.transform((W, H), Image.AFFINE, (s, 0, cx - w / 2, 0, s, cy - h / 2),
                         resample=Image.BICUBIC)


starts, t = [], 0.0
for sh in SHOTS:
    starts.append(t)
    t += sh[1] - XF
total = t + XF
nframes = int(round(total * FPS))


def shot_frame(i, tt):
    k, dur, a, b = SHOTS[i]
    u = ease(min(max((tt - starts[i]) / dur, 0), 1))
    return frame(src[k], *[a[j] + (b[j] - a[j]) * u for j in range(3)])


# subtle vignette
yy, xx = np.mgrid[0:H, 0:W]
r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
vig = (1 - 0.18 * np.clip(r - 0.55, 0, 1) ** 1.5)[..., None].astype(np.float32)




# ---------- music ----------
def make_music(seconds, sr=44100):
    n = int(seconds * sr)
    out = np.zeros((n, 2))
    tt = np.arange(n) / sr
    bpm = 96
    beat = 60 / bpm
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    chords = [[48, 55, 64, 71], [45, 52, 60, 67], [41, 48, 57, 64], [43, 50, 59, 62]]  # Cmaj7 Am7 Fmaj7 G
    bar = 4 * beat
    rng = np.random.default_rng(7)
    # pad
    for ci in range(int(seconds / bar) + 1):
        ch = chords[ci % 4]
        s0, s1 = int(ci * bar * sr), min(int((ci + 1) * bar * sr + 0.6 * sr), n)
        if s0 >= n:
            break
        lt = tt[s0:s1] - ci * bar
        env = np.minimum(lt / 0.8, 1) * np.minimum((s1 / sr - ci * bar - lt) / 0.6, 1)
        for m in ch:
            for det, pan in ((-0.08, 0.3), (0.08, 0.7)):
                f = hz(m + det)
                v = (np.sin(2 * np.pi * f * lt) + 0.3 * np.sin(4 * np.pi * f * lt)) * env * 0.035
                out[s0:s1, 0] += v * (1 - pan)
                out[s0:s1, 1] += v * pan
    # plucked arpeggio (Karplus-Strong), starts after intro
    def pluck(f, dur=1.2):
        L = int(sr / f)
        buf = rng.uniform(-1, 1, L)
        o = np.zeros(int(dur * sr))
        for i in range(len(o)):
            o[i] = buf[i % L]
            buf[i % L] = 0.996 * 0.5 * (buf[i % L] + buf[(i + 1) % L])
        return o
    cache = {}
    step = beat / 2
    t0 = 2 * bar
    k = 0
    while t0 + k * step < seconds - 1.5:
        tk = t0 + k * step
        ch = chords[int(tk / bar) % 4]
        m = (ch + [c + 12 for c in ch])[[0, 2, 4, 3, 5, 2, 6, 4][k % 8] % 8] + 12
        if m not in cache:
            cache[m] = pluck(hz(m))
        p = cache[m]
        s0 = int(tk * sr)
        e = min(s0 + len(p), n)
        pan = 0.35 + 0.3 * (k % 2)
        out[s0:e, 0] += p[:e - s0] * 0.12 * (1 - pan)
        out[s0:e, 1] += p[:e - s0] * 0.12 * pan
        k += 1
    # soft kick + shaker
    kb = 0
    while 2 * bar + kb * beat < seconds - 1.0:
        tk = 2 * bar + kb * beat
        s0 = int(tk * sr)
        L = int(0.35 * sr)
        e = min(s0 + L, n)
        lt = np.arange(e - s0) / sr
        if kb % 2 == 0:
            kick = np.sin(2 * np.pi * (50 * lt + 60 * (1 - np.exp(-lt * 30)) / 30)) * np.exp(-lt * 9)
            out[s0:e] += (kick * 0.22)[:, None]
        s1 = int((tk + beat / 2) * sr)
        Ls = min(int(0.08 * sr), n - s1)
        if Ls > 0:
            sh = rng.uniform(-1, 1, Ls) * np.exp(-np.arange(Ls) / sr * 45)
            sh = np.diff(sh, prepend=0)
            out[s1:s1 + Ls, 0] += sh * 0.03
            out[s1:s1 + Ls, 1] += sh * 0.04
        kb += 1
    fade = np.minimum(np.minimum(tt / 1.5, 1), np.minimum((seconds - tt) / 2.5, 1))
    out *= fade[:, None]
    out /= np.abs(out).max() / 0.85
    with wave.open(f"{OUT}.wav", "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((out * 32767).astype(np.int16).tobytes())


make_music(total)
ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                       "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", f"{OUT}.wav",
                       "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", OUT],
                      stdin=subprocess.PIPE)

for fi in range(nframes):
    tt = fi / FPS
    active = [i for i in range(len(SHOTS)) if starts[i] <= tt < starts[i] + SHOTS[i][1]]
    if len(active) == 1:
        a = np.asarray(shot_frame(active[0], tt), np.float32)
    else:
        i, j = active[0], active[-1]
        m = ease((tt - starts[j]) / XF)
        a = np.asarray(shot_frame(i, tt), np.float32) * (1 - m) + np.asarray(shot_frame(j, tt), np.float32) * m
    a = a * vig
    a *= min(tt / 0.8, 1) * min((total - tt) / 1.2, 1)
    ff.stdin.write(np.clip(a, 0, 255).astype(np.uint8).tobytes())
ff.stdin.close()
ff.wait()
print("frames", nframes, "seconds", total)
