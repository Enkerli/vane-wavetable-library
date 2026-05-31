#!/usr/bin/env python3
"""Basic wavetable analysis helper for Vane curation.

This script intentionally uses only the Python standard library. It reports
simple frame-to-frame continuity and RMS values. More advanced spectral metrics
can be added later with numpy/scipy/librosa.
"""

from __future__ import annotations

import argparse
import math
import wave
from pathlib import Path
import struct


def read_wav(path: Path) -> tuple[int, list[float]]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())

    samples: list[float] = []
    if width == 2:
        fmt = "<" + "h" * (len(frames) // 2)
        raw = struct.unpack(fmt, frames)
        samples = [x / 32768.0 for i, x in enumerate(raw) if i % channels == 0]
    elif width == 4:
        # Try float32 first. Some WAVs may be int32; this starter keeps it simple.
        fmt = "<" + "f" * (len(frames) // 4)
        raw = struct.unpack(fmt, frames)
        samples = [float(x) for i, x in enumerate(raw) if i % channels == 0]
    else:
        raise ValueError(f"Unsupported sample width: {width}")
    return rate, samples


def rms(frame: list[float]) -> float:
    return math.sqrt(sum(x * x for x in frame) / len(frame))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--frame-length", type=int, default=2048)
    args = parser.parse_args()

    rate, samples = read_wav(Path(args.path))
    frame_count = len(samples) // args.frame_length
    frames = [samples[i * args.frame_length:(i + 1) * args.frame_length] for i in range(frame_count)]

    rms_values = [rms(f) for f in frames]
    similarities = [cosine_similarity(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]

    print(f"Path: {args.path}")
    print(f"Sample rate: {rate}")
    print(f"Frame length: {args.frame_length}")
    print(f"Frame count: {frame_count}")
    print(f"RMS min/max: {min(rms_values):.4f} / {max(rms_values):.4f}")
    if similarities:
        print(f"Adjacent similarity avg/min: {sum(similarities)/len(similarities):.4f} / {min(similarities):.4f}")


if __name__ == "__main__":
    main()
