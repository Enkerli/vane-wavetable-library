#!/usr/bin/env python3
"""Generate simple Vane candidate wavetables.

This starter script writes mono floating-point WAV files containing stacked
single-cycle frames. It is meant for candidate generation, not automatic curation.
"""

from __future__ import annotations

import argparse
import math
import wave
from pathlib import Path
import struct


def normalize(frame: list[float]) -> list[float]:
    peak = max(abs(x) for x in frame) or 1.0
    return [x / peak for x in frame]


def harmonic_growth(frame_count: int, frame_length: int, max_harmonics: int) -> list[float]:
    all_samples: list[float] = []
    for frame_index in range(frame_count):
        t = frame_index / max(frame_count - 1, 1)
        harmonic_limit = 1 + round(t * (max_harmonics - 1))
        spectral_slope = 1.8 - 1.1 * t  # darker at start, brighter at end
        frame = []
        for n in range(frame_length):
            phase = 2.0 * math.pi * n / frame_length
            value = 0.0
            for h in range(1, harmonic_limit + 1):
                amp = 1.0 / (h ** spectral_slope)
                value += amp * math.sin(h * phase)
            frame.append(value)
        all_samples.extend(normalize(frame))
    return all_samples


def write_float_wav(path: Path, samples: list[float], sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(4)
        wav.setframerate(sample_rate)
        for x in samples:
            wav.writeframes(struct.pack("<f", max(-1.0, min(1.0, x))))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="wavetables/generated/vane_generated_harmonic_growth_001.wav")
    parser.add_argument("--frames", type=int, default=32)
    parser.add_argument("--frame-length", type=int, default=2048)
    parser.add_argument("--max-harmonics", type=int, default=32)
    parser.add_argument("--sample-rate", type=int, default=44100)
    args = parser.parse_args()

    samples = harmonic_growth(args.frames, args.frame_length, args.max_harmonics)
    write_float_wav(Path(args.out), samples, args.sample_rate)
    print(f"Wrote {args.out} ({args.frames} frames × {args.frame_length} samples)")


if __name__ == "__main__":
    main()
