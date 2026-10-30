"""Synthesize five original PCM signals; no downloaded sound samples."""

import math
import pathlib
import struct
import wave

rate = 48000
patterns = {
    "chime": ([(0, 784), (0.65, 988), (1.3, 1175)], 2.3, 5, 0.18),
    "bell": ([(0, 1047), (1.0, 1047)], 2.7, 3.7, 0.4),
    "digital": ([(n * 0.23, 1100 if n % 2 == 0 else 880) for n in range(6)], 1.7, 14, 0.08),
    "piano": ([(0, 523), (0.4, 659), (0.8, 784), (1.2, 1047)], 2.8, 4, 0.10),
    "gong": ([(0, 330), (0.03, 495)], 3.0, 1.8, 0.32),
}
for name, (notes, length, decay, harmonic) in patterns.items():
    samples = []
    for i in range(round(rate * length)):
        t = i / rate
        value = 0
        for start, freq in notes:
            dt = t - start
            tail = 0.8 if name in ["chime", "digital"] else length - start
            if 0 <= dt < tail:
                envelope = min(1, dt / 0.015) * math.exp(-decay * dt) * min(1, (tail - dt) / 0.06)
                value += (
                    0.65
                    * envelope
                    * (
                        math.sin(2 * math.pi * freq * dt)
                        + harmonic * math.sin(2 * math.pi * freq * 2 * dt)
                    )
                    / (1 + harmonic)
                )
        samples.append(struct.pack("<h", max(-32767, min(32767, round(32767 * value)))))
    with wave.open(str(pathlib.Path("app/static") / ("timer-" + name + ".wav")), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"".join(samples))
print("Generated five timer signals")
