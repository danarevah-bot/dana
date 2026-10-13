"""Synthesize a soft, warm background track (stereo WAV): mellow keys, pad and sub bass.

No noise-based percussion and a low-passed master so nothing is harsh on the ears.
Usage: python3 music.py <seconds> <out.wav>
"""
import sys, wave
import numpy as np

SR = 44100
DUR = float(sys.argv[1])
OUT = sys.argv[2]
BPM = 86
BEAT = 60 / BPM
N = int(SR * (DUR + 2))
L = np.zeros(N); R = np.zeros(N)


def midi(m): return 440 * 2 ** ((m - 69) / 12)


def add(start, sig, gain, pan=0.0):
    i = int(start * SR)
    if i >= N: return
    sig = sig[: N - i]
    L[i:i + len(sig)] += sig * gain * (1 - pan)
    R[i:i + len(sig)] += sig * gain * (1 + pan)


def keys(freq, dur=1.6):
    """Soft electric-piano-like tone: sine body, faint 2nd harmonic, gentle attack."""
    n = int(SR * dur); t = np.arange(n) / SR
    body = np.sin(2 * np.pi * freq * t) + 0.18 * np.sin(4 * np.pi * freq * t) * np.exp(-t * 6)
    env = np.minimum(1, t / 0.012) * np.exp(-t * 2.2)
    rel = np.clip((dur - t) / 0.3, 0, 1)
    return body * env * rel


def pad(freqs, dur):
    n = int(SR * dur); t = np.arange(n) / SR
    sig = sum(np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.004 * t + 1.0) for f in freqs)
    env = np.minimum(1, t / 0.9) * np.clip((dur - t) / 0.9, 0, 1)
    return sig * env / len(freqs)


def bass(freq, dur):
    n = int(SR * dur); t = np.arange(n) / SR
    env = np.minimum(1, t / 0.03) * np.exp(-t * 1.2) * np.clip((dur - t) / 0.15, 0, 1)
    return np.sin(2 * np.pi * freq * t) * env


def thump():
    """Very soft, round low kick (no click)."""
    n = int(SR * 0.4); t = np.arange(n) / SR
    f = 48 + 30 * np.exp(-t * 18)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.minimum(1, t / 0.006) * np.exp(-t * 8)


# Cmaj7 - Am7 - Fmaj7 - G(add9)
prog = [
    ([48], [60, 64, 67, 71]),
    ([45], [57, 60, 64, 67]),
    ([41], [57, 60, 65, 69]),
    ([43], [55, 59, 62, 69]),
]
arp = [0, 2, 1, 3, 2, 1]  # gentle broken chord in 3/4 feel over each bar of 4 beats
bar = 4 * BEAT
t0, b = 0.0, 0
GROOVE_IN = 3.2
while t0 < DUR + bar:
    bass_n, chord = prog[b % 4]
    add(t0, pad([midi(m) for m in chord], bar + 0.9), 0.07)
    for k, idx in enumerate(arp):
        st = t0 + k * (bar / len(arp))
        add(st, keys(midi(chord[idx] + 12)), 0.11, pan=0.25 if k % 2 else -0.25)
    if t0 >= GROOVE_IN - 0.01:
        add(t0, bass(midi(bass_n[0]), bar * 0.95), 0.22)
        for beat in (0, 2):
            add(t0 + beat * BEAT, thump(), 0.20)
    t0 += bar
    b += 1

# soft room: a couple of quiet, low-passed echoes
def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    from itertools import accumulate
    out = list(accumulate(x, lambda p, v: a * p + (1 - a) * v, initial=0.0))[1:]
    return np.array(out)

for delay, g in ((0.23, 0.18), (0.41, 0.12)):
    d = int(SR * delay)
    L[d:] += g * R[:-d]; R[d:] += g * L[:-d]

L = lowpass(L, 3200)[: int(SR * DUR)]
R = lowpass(R, 3200)[: int(SR * DUR)]

t = np.arange(len(L)) / SR
fade = np.minimum(1, t / 1.5) * np.clip((DUR - t) / 3.0, 0, 1)
L *= fade; R *= fade
peak = max(np.abs(L).max(), np.abs(R).max())
gain = 0.5 / peak  # peak around -6 dBFS: comfortable listening level
data = (np.stack([L, R], 1) * gain * 32767).astype(np.int16)
with wave.open(OUT, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(data.tobytes())
print("wrote", OUT, DUR)
