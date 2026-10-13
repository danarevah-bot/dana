"""Synthesize a light, upbeat royalty-free background track (stereo WAV)."""
import sys, wave
import numpy as np

SR = 44100
DUR = float(sys.argv[1])
OUT = sys.argv[2]
BPM = 112
BEAT = 60 / BPM
N = int(SR * (DUR + 1))
L = np.zeros(N); R = np.zeros(N)
rng = np.random.default_rng(7)

def midi(m): return 440 * 2 ** ((m - 69) / 12)

def add(buf, start, sig, gain=1.0):
    i = int(start * SR)
    if i >= N: return
    sig = sig[: N - i]
    buf[i:i + len(sig)] += sig * gain

def pluck(freq, dur=0.9, decay=0.996, bright=0.5):
    p = int(SR / freq)
    n = int(SR * dur)
    y = np.zeros(n + p)
    y[:p] = rng.uniform(-1, 1, p)
    # low-pass the excitation for a softer tone
    for _ in range(int(3 * (1 - bright)) + 1):
        y[:p] = 0.5 * (y[:p] + np.roll(y[:p], 1))
    for s in range(p, n + p, p):
        e = min(s + p, n + p)
        seg = y[s - p:e - p]
        prev = np.concatenate(([y[s - p - 1] if s - p - 1 >= 0 else 0], seg[:-1]))
        y[s:e] = decay * 0.5 * (seg + prev)
    y = y[:n]
    env = np.minimum(1, np.linspace(0, n / SR, n) / 0.003)
    return y * env

def pad(freqs, dur):
    n = int(SR * dur); t = np.arange(n) / SR
    sig = sum(np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t) + 0.08 * np.sin(2 * np.pi * f * 1.003 * t) for f in freqs)
    a = 0.4
    env = np.minimum(1, t / a) * np.minimum(1, (dur - t) / 0.4)
    return sig * env / len(freqs)

def kick():
    n = int(SR * 0.35); t = np.arange(n) / SR
    f = 50 + 90 * np.exp(-t * 30)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 9)

def shaker(dur=0.06):
    n = int(SR * dur); t = np.arange(n) / SR
    s = rng.uniform(-1, 1, n)
    s = s - np.concatenate(([0], s[:-1]))  # crude high-pass
    return s * np.exp(-t * 60)

def snap():
    n = int(SR * 0.15); t = np.arange(n) / SR
    s = rng.uniform(-1, 1, n)
    s = 0.5 * (s + np.concatenate(([0], s[:-1])))
    return s * np.exp(-t * 35) + 0.4 * np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 60)

# C - G - Am - F  (I V vi IV)
prog = [
    (60, [60, 64, 67, 72], 36),
    (55, [59, 62, 67, 71], 43),
    (57, [57, 60, 64, 69], 45),
    (53, [57, 60, 65, 69], 41),
]
arp_pattern = [0, 1, 2, 3, 2, 1, 2, 3]
bar = 4 * BEAT
t0 = 0.0
b = 0
DRUMS_IN = 3.3
while t0 < DUR:
    _, chord, bass = prog[b % 4]
    # pad
    p = pad([midi(m - 12) for m in chord[:3]], bar + 0.3)
    add(L, t0, p, 0.10); add(R, t0, p, 0.10)
    # arpeggio (8ths), alternating slight panning
    for k, idx in enumerate(arp_pattern):
        st = t0 + k * BEAT / 2
        note = chord[idx] + 12
        s = pluck(midi(note), 0.8, 0.995, 0.6)
        pan = 0.35 if k % 2 else -0.35
        add(L, st, s, 0.16 * (1 - pan)); add(R, st, s, 0.16 * (1 + pan))
    # bass
    if t0 >= DRUMS_IN - 0.01:
        for beat in (0, 1.5, 2, 3.5):
            s = pluck(midi(bass), 0.5, 0.997, 0.2)
            add(L, t0 + beat * BEAT, s, 0.30); add(R, t0 + beat * BEAT, s, 0.30)
        for beat in range(4):
            st = t0 + beat * BEAT
            if beat in (0, 2):
                add(L, st, kick(), 0.55); add(R, st, kick(), 0.55)
            else:
                sn = snap()
                add(L, st, sn, 0.16); add(R, st, sn, 0.16)
        for e in range(8):
            sh = shaker()
            g = 0.06 if e % 2 else 0.035
            add(L, t0 + e * BEAT / 2, sh, g * 0.8); add(R, t0 + e * BEAT / 2, sh, g * 1.2)
    t0 += bar
    b += 1

# simple stereo echo for space
d = int(SR * BEAT * 0.75)
L2 = L.copy(); R2 = R.copy()
L2[d:] += 0.22 * R[:-d]; R2[d:] += 0.22 * L[:-d]
L, R = L2[: int(SR * DUR)], R2[: int(SR * DUR)]

n = len(L); t = np.arange(n) / SR
fade = np.minimum(1, t / 0.8) * np.clip((DUR - t) / 2.5, 0, 1)
L *= fade; R *= fade
peak = max(np.abs(L).max(), np.abs(R).max())
L = L / peak * 0.85; R = R / peak * 0.85
# gentle soft clip
L = np.tanh(L * 1.1) / np.tanh(1.1); R = np.tanh(R * 1.1) / np.tanh(1.1)
data = (np.stack([L, R], 1) * 32000).astype(np.int16)
with wave.open(OUT, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(data.tobytes())
print("wrote", OUT, DUR)
