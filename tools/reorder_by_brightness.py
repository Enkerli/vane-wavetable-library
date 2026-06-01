#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reorder_by_brightness.py

Sort wavetable frames from darkest to brightest by spectral centroid,
producing a simple → intense morph trajectory suitable for breath or MPE slide.

Two modes:

  Single-cycle folder (AKWF style):
    Each WAV in the folder is one frame.  Reads all, sorts by centroid,
    concatenates into a single output wavetable.

      python tools/reorder_by_brightness.py upstream/AKWF/AKWF_add \
        --frame-size 2048 --out source/AKWF/candidates/add_bright.wav

  Multi-frame wavetable:
    A single WAV containing N×frame_size samples.  Splits, sorts, rewrites.

      python tools/reorder_by_brightness.py source/AKWF/candidates/akwf_AKWF_add_001.wav \
        --frame-size 2048 --out source/AKWF/candidates/akwf_AKWF_add_001_sorted.wav

Output is always mono 32-bit float WAV (Vane native format).
A JSON sidecar next to the output records per-frame centroid values and
the original filenames/indices so the ordering is inspectable.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import numpy as np


# ── I/O ──────────────────────────────────────────────────────────────────────

def read_f32_wav(path: Path) -> tuple[np.ndarray, int]:
    """Read any PCM or IEEE-float WAV as float32 mono."""
    with open(path, "rb") as f:
        raw = f.read()

    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError(f"Not a RIFF/WAVE file: {path}")

    fmt_tag = channels = sample_rate = bits = 0
    data_bytes = b""
    i = 12
    while i + 8 <= len(raw):
        chunk_id = raw[i:i+4]
        chunk_size = struct.unpack_from("<I", raw, i+4)[0]
        body = raw[i+8: i+8+chunk_size]
        if chunk_id == b"fmt ":
            fmt_tag, channels, sample_rate = struct.unpack_from("<HHI", body, 0)
            bits = struct.unpack_from("<H", body, 14)[0]
        elif chunk_id == b"data":
            data_bytes = body
        i += 8 + chunk_size + (chunk_size & 1)

    if fmt_tag == 3 and bits == 32:
        samples = np.frombuffer(data_bytes, dtype="<f4").astype(np.float32)
    elif fmt_tag == 1 and bits == 16:
        samples = np.frombuffer(data_bytes, dtype="<i2").astype(np.float32) / 32768.0
    elif fmt_tag == 1 and bits == 24:
        b = np.frombuffer(data_bytes, dtype=np.uint8).reshape(-1, 3)
        s = b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16)
        s = np.where(s & 0x800000, s - 0x1000000, s)
        samples = s.astype(np.float32) / 8388608.0
    elif fmt_tag == 1 and bits == 32:
        samples = np.frombuffer(data_bytes, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported format tag={fmt_tag} bits={bits} in {path}")

    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)

    return samples, sample_rate


def write_f32_wav(path: Path, data: np.ndarray, sample_rate: int = 44100) -> None:
    """Write mono 32-bit float WAV — matches Vane's native saveToWav format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = data.astype("<f4")
    data_bytes = pcm.tobytes()
    data_size = len(data_bytes)
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write((36 + data_size).to_bytes(4, "little"))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write((16).to_bytes(4, "little"))
        f.write((3).to_bytes(2, "little"))             # IEEE float
        f.write((1).to_bytes(2, "little"))             # mono
        f.write(sample_rate.to_bytes(4, "little"))
        f.write((sample_rate * 4).to_bytes(4, "little"))
        f.write((4).to_bytes(2, "little"))
        f.write((32).to_bytes(2, "little"))
        f.write(b"data")
        f.write(data_size.to_bytes(4, "little"))
        f.write(data_bytes)


# ── Spectral centroid ─────────────────────────────────────────────────────────

def spectral_centroid(frame: np.ndarray) -> float:
    """
    Frequency-weighted mean of the magnitude spectrum, normalized to 0..1
    (0 = DC, 1 = Nyquist).  Higher = brighter / more high-frequency content.
    """
    mag = np.abs(np.fft.rfft(frame * np.hanning(len(frame))))
    mag[0] = 0.0  # drop DC
    total = float(np.sum(mag)) + 1e-12
    freqs = np.linspace(0.0, 1.0, len(mag))
    return float(np.sum(freqs * mag) / total)


def normalize_frame(x: np.ndarray) -> np.ndarray:
    x = x - float(np.mean(x))
    peak = float(np.max(np.abs(x)))
    return (x / peak).astype(np.float32) if peak > 0 else x.astype(np.float32)


def resample_to(x: np.ndarray, size: int) -> np.ndarray:
    if len(x) == size:
        return x.astype(np.float32)
    old = np.linspace(0.0, 1.0, len(x), endpoint=False)
    new = np.linspace(0.0, 1.0, size, endpoint=False)
    return np.interp(new, np.append(old, 1.0), np.append(x, x[0])).astype(np.float32)


# ── Modes ─────────────────────────────────────────────────────────────────────

def load_folder(folder: Path, frame_size: int) -> tuple[list[np.ndarray], list[str], int]:
    paths = sorted(p for p in folder.iterdir()
                   if p.suffix.lower() == ".wav")
    if not paths:
        raise SystemExit(f"No WAV files found in {folder}")

    frames, names, rate = [], [], 44100
    for p in paths:
        try:
            raw, sr = read_f32_wav(p)
            rate = sr
            frame = normalize_frame(resample_to(raw, frame_size))
            frames.append(frame)
            names.append(p.name)
        except Exception as e:
            print(f"  skipping {p.name}: {e}")

    return frames, names, rate


def load_wavetable(wav_path: Path, frame_size: int) -> tuple[list[np.ndarray], list[str], int]:
    raw, rate = read_f32_wav(wav_path)
    n_frames = len(raw) // frame_size
    if n_frames == 0:
        raise SystemExit(f"{wav_path}: file too short for frame_size={frame_size}")

    frames, names = [], []
    for i in range(n_frames):
        frame = normalize_frame(raw[i * frame_size: (i + 1) * frame_size].copy())
        frames.append(frame)
        names.append(f"frame_{i:03d}")

    return frames, names, rate


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sort wavetable frames dark→bright by spectral centroid."
    )
    parser.add_argument("input", type=Path,
                        help="Folder of single-cycle WAVs, or a multi-frame wavetable WAV.")
    parser.add_argument("--out", type=Path, required=True,
                        help="Output wavetable WAV path.")
    parser.add_argument("--frame-size", type=int, default=2048,
                        help="Samples per frame (default: 2048).")
    parser.add_argument("--reverse", action="store_true",
                        help="Sort bright→dark instead (descending centroid).")
    parser.add_argument("--max-frames", type=int, default=0,
                        help="Cap output at N frames (0 = all).")
    args = parser.parse_args()

    if args.input.is_dir():
        print(f"Mode: folder of single-cycle WAVs — {args.input}")
        frames, names, rate = load_folder(args.input, args.frame_size)
    else:
        print(f"Mode: multi-frame wavetable — {args.input}")
        frames, names, rate = load_wavetable(args.input, args.frame_size)

    centroids = [spectral_centroid(f) for f in frames]
    order = sorted(range(len(frames)), key=lambda i: centroids[i],
                   reverse=args.reverse)

    if args.max_frames and args.max_frames < len(order):
        # Evenly subsample to keep coverage across the brightness range.
        indices = np.round(np.linspace(0, len(order) - 1, args.max_frames)).astype(int)
        order = [order[i] for i in indices]

    sorted_frames = [frames[i] for i in order]

    # Normalize the full table together so relative loudness is preserved.
    all_data = np.concatenate(sorted_frames)
    peak = float(np.max(np.abs(all_data)))
    if peak > 0:
        all_data = all_data / peak * 0.98

    write_f32_wav(args.out, all_data, rate)

    # Sidecar JSON.
    sidecar = args.out.with_suffix(".json")
    report = {
        "source": str(args.input),
        "frame_size": args.frame_size,
        "frame_count": len(order),
        "direction": "bright_to_dark" if args.reverse else "dark_to_bright",
        "frames": [
            {"index": i, "source_name": names[idx], "centroid": round(centroids[idx], 6)}
            for i, idx in enumerate(order)
        ],
    }
    sidecar.write_text(json.dumps(report, indent=2))

    print(f"Wrote {len(order)} frames → {args.out}")
    print(f"Centroid range: {centroids[order[0]]:.4f} → {centroids[order[-1]]:.4f}")
    print(f"Sidecar:        {sidecar}")


if __name__ == "__main__":
    main()
