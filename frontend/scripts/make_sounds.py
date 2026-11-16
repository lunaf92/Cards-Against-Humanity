"""Generate the game's sound effects as small WAV files (original, synthesized, no samples).

    python3 frontend/scripts/make_sounds.py

Any file in public/sounds/ can be swapped for a recorded one with the same name.
"""
import math
import random
import struct
import wave
from pathlib import Path

RATE = 22050
OUT = Path(__file__).resolve().parent.parent / "public" / "sounds"


def env(i, n, attack=0.005, release=0.6):
    """Linear attack, exponential-ish release over n samples."""
    t = i / RATE
    a = min(1.0, t / attack) if attack > 0 else 1.0
    r = (1 - i / n) ** (1 / max(release, 1e-3))
    return a * r


def tone(freq, dur, vol=0.5, shape="sine", f_end=None, release=0.6):
    n = int(RATE * dur)
    out, phase = [], 0.0
    for i in range(n):
        f = freq if f_end is None else freq + (f_end - freq) * i / n
        phase += 2 * math.pi * f / RATE
        if shape == "sine":
            s = math.sin(phase)
        elif shape == "tri":
            s = 2 / math.pi * math.asin(math.sin(phase))
        else:  # soft square
            s = math.tanh(3 * math.sin(phase))
        out.append(vol * s * env(i, n, release=release))
    return out


def noise(dur, vol=0.4, lowpass=0.15):
    n = int(RATE * dur)
    out, y = [], 0.0
    for i in range(n):
        y += lowpass * (random.uniform(-1, 1) - y)
        out.append(vol * y * 4 * env(i, n, attack=0.002, release=0.35))
    return out


def seq(*parts, gap=0.0):
    out = []
    for p in parts:
        out += p + [0.0] * int(RATE * gap)
    return out


def mix(*tracks):
    n = max(len(t) for t in tracks)
    return [sum(t[i] for t in tracks if i < len(t)) for i in range(n)]


def save(name, samples):
    peak = max(1e-9, max(abs(s) for s in samples))
    scale = min(1.0, 0.9 / peak)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(s * scale * 32767)) for s in samples))


NOTE = {"C5": 523.25, "E5": 659.25, "G5": 783.99, "C6": 1046.5, "E6": 1318.5, "G6": 1568.0, "A5": 880.0, "D6": 1174.7}

random.seed(7)
OUT.mkdir(parents=True, exist_ok=True)
# Card slapped onto the table: a short brushed noise plus a low thump.
save("play", mix(noise(0.09, 0.5, 0.25), tone(140, 0.07, 0.5, f_end=90, release=0.4)))
# Card lifted into the zoom viewer: a soft rising pop.
save("zoom", tone(520, 0.07, 0.35, f_end=880, release=0.5))
# Every answer is in: two-note chime.
save("all_in", seq(tone(NOTE["C6"], 0.12, 0.35, "tri"), tone(NOTE["E6"], 0.22, 0.35, "tri"), gap=0.01))
# You're the judge this round: three-note rising call.
save("judge", seq(tone(NOTE["G5"], 0.09, 0.35, "tri"), tone(NOTE["C6"], 0.09, 0.35, "tri"), tone(NOTE["E6"], 0.2, 0.35, "tri")))
# Someone else won the round: single bell.
save("round", mix(tone(NOTE["A5"], 0.35, 0.35, "sine", release=0.4), tone(NOTE["A5"] * 2, 0.25, 0.12, release=0.3)))
# You won the round: bright arpeggio.
save("round_win", seq(*(tone(NOTE[n], 0.08 if n != "C6" else 0.3, 0.35, "square", release=0.5) for n in ("C5", "E5", "G5", "C6"))))
# Last seconds of the timer.
save("tick", tone(1400, 0.03, 0.3, "square", release=0.3))
# Reaction bubble popping up.
save("reaction", tone(320, 0.06, 0.4, f_end=760, release=0.45))
# Game over fanfare.
save("game_over", seq(
    tone(NOTE["C5"], 0.12, 0.35, "square"), tone(NOTE["C5"], 0.12, 0.35, "square"),
    tone(NOTE["E5"], 0.12, 0.35, "square"), tone(NOTE["G5"], 0.2, 0.35, "square"),
    mix(tone(NOTE["C6"], 0.6, 0.3, "square", release=0.7), tone(NOTE["E6"], 0.6, 0.15, "tri", release=0.7)),
    gap=0.02,
))
print("wrote", sorted(p.name for p in OUT.glob("*.wav")))
