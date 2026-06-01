#!/usr/bin/env python3
"""
build_akwf_tables.py

Build Vane wavetable candidates from AKWF-style single-cycle WAV files.

Goal:
- Convert many single-cycle waveforms into candidate wavetables.
- Order frames from simpler/darker to more complex/brighter.
- Prefer adjacent frames that are similar enough for smooth interpolation.
- Emit JSON metadata so every generated table remains inspectable.

Assumptions:
- Input WAVs are mono or stereo PCM. Stereo is averaged to mono.
- Each source file is treated as a single-cycle waveform.
- Output is a mono PCM WAV containing frames concatenated back-to-back.

Example:
    python tools/build_akwf_tables.py upstream/AKWF/AKWF_add \
      --frames 32 \
      --frame-size 2048 \
      --tables 8 \
      --out source/AKWF/candidates/additive \
      --metadata metadata/akwf_candidates_additive.json

For Vane:
- These are candidates, not curated tables.
- Audition with CC02 breath and MPE slide before promoting to curated/.
"""

from __future__ import annotations

import argparse
import json
import math
import wave
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import numpy as np


@dataclass
class WaveMetrics:
    path: str
    filename: str
    rms: float
    peak: float
    dc: float
    zero_crossing_rate: float
    spectral_centroid: float
    spectral_flatness: float
    harmonic_richness: float
    odd_even_balance: float
    complexity: float


@dataclass
class TableMetadata:
    id: str
    origin: str
    source_collection: str
    source_folder: str
    license: str
    curation_status: str
    frame_count: int
    frame_size: int
    output_wav: str
    build_strategy: str
    adjacency_distance_mean: float
    adjacency_distance_max: float
    complexity_min: float
    complexity_max: float
    spectral_centroid_min: float
    spectral_centroid_max: float
    monotonicity_score: float
    continuity_score: float
    primary_controllers: list[str]
    source_files: list[str]
    notes: str


def read_pcm_wav(path: Path) -> tuple[np.ndarray, int]:
    """Read PCM WAV as float32 mono in [-1, 1]."""
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        frames = wf.getnframes()
        raw = wf.readframes(frames)

    if sample_width == 1:
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        data = (data - 128.0) / 128.0
    elif sample_width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 3:
        # 24-bit little-endian PCM
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        signed = (
            b[:, 0].astype(np.int32)
            | (b[:, 1].astype(np.int32) << 8)
            | (b[:, 2].astype(np.int32) << 16)
        )
        signed = np.where(signed & 0x800000, signed - 0x1000000, signed)
        data = signed.astype(np.float32) / 8388608.0
    elif sample_width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {sample_width} bytes in {path}")

    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)

    return data.astype(np.float32), sample_rate


def remove_dc_and_normalize(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32)
    x = x - float(np.mean(x))
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak > 0:
        x = x / peak
    return x


def resample_cycle(x: np.ndarray, size: int) -> np.ndarray:
    """Periodic linear resample of one cycle to fixed frame size."""
    if len(x) == size:
        return x.astype(np.float32)
    old = np.linspace(0.0, 1.0, num=len(x), endpoint=False)
    new = np.linspace(0.0, 1.0, num=size, endpoint=False)
    xp = np.concatenate([old, [1.0]])
    fp = np.concatenate([x, [x[0]]])
    return np.interp(new, xp, fp).astype(np.float32)


def align_to_reference(candidate: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """
    Circularly shift and optionally polarity-flip candidate to best match reference.
    This reduces artificial discontinuity between adjacent frames.
    """
    if len(candidate) != len(reference):
        raise ValueError("candidate and reference must have same length")

    c = candidate - np.mean(candidate)
    r = reference - np.mean(reference)

    corr = np.fft.ifft(np.fft.fft(c) * np.conj(np.fft.fft(r))).real
    shift = int(np.argmax(corr))
    shifted = np.roll(candidate, -shift)

    # Polarity check
    if np.linalg.norm((-shifted) - reference) < np.linalg.norm(shifted - reference):
        shifted = -shifted

    return shifted.astype(np.float32)


def spectrum(x: np.ndarray) -> np.ndarray:
    win = np.hanning(len(x))
    mag = np.abs(np.fft.rfft(x * win))
    return mag + 1e-12


def compute_metrics(path: Path, x: np.ndarray) -> WaveMetrics:
    mag = spectrum(x)
    freqs = np.linspace(0.0, 1.0, len(mag))  # normalized Nyquist range
    mag_no_dc = mag.copy()
    mag_no_dc[0] = 0.0

    total = float(np.sum(mag_no_dc)) + 1e-12
    centroid = float(np.sum(freqs * mag_no_dc) / total)

    geom = float(np.exp(np.mean(np.log(mag_no_dc[1:] + 1e-12))))
    arith = float(np.mean(mag_no_dc[1:] + 1e-12))
    flatness = geom / arith if arith > 0 else 0.0

    zc = float(np.mean(np.diff(np.signbit(x)) != 0))
    rms = float(np.sqrt(np.mean(x * x)))
    peak = float(np.max(np.abs(x)))
    dc = float(np.mean(x))

    # Crude harmonic richness: proportion of bins above -40 dB from peak.
    mmax = float(np.max(mag_no_dc)) + 1e-12
    harmonic_richness = float(np.mean(mag_no_dc > (mmax * 0.01)))

    # Odd/even balance over approximate harmonic bins.
    # This is intentionally approximate because AKWF cycles vary in length/source.
    harmonics = mag_no_dc[1:65]
    odd = float(np.sum(harmonics[0::2])) + 1e-12
    even = float(np.sum(harmonics[1::2])) + 1e-12
    odd_even_balance = float(math.log2(odd / even))

    # Tuned to sort from sine-like/dark/smooth to brighter/noisier/more complex.
    complexity = (
        0.45 * centroid
        + 0.25 * min(flatness * 3.0, 1.0)
        + 0.20 * min(zc * 8.0, 1.0)
        + 0.10 * min(harmonic_richness * 8.0, 1.0)
    )

    return WaveMetrics(
        path=str(path),
        filename=path.name,
        rms=rms,
        peak=peak,
        dc=dc,
        zero_crossing_rate=zc,
        spectral_centroid=centroid,
        spectral_flatness=flatness,
        harmonic_richness=harmonic_richness,
        odd_even_balance=odd_even_balance,
        complexity=float(complexity),
    )


def frame_distance(a: np.ndarray, b: np.ndarray) -> float:
    """
    Combined time-domain and spectral distance.
    Lower means smoother adjacent morphing.
    """
    td = float(np.sqrt(np.mean((a - b) ** 2)))
    sa = spectrum(a)
    sb = spectrum(b)
    sa = sa / (np.sum(sa) + 1e-12)
    sb = sb / (np.sum(sb) + 1e-12)
    sd = float(np.sqrt(np.mean((np.log(sa + 1e-12) - np.log(sb + 1e-12)) ** 2)))
    return 0.65 * td + 0.35 * min(sd / 10.0, 1.0)


def choose_sequence(
    waves: list[np.ndarray],
    metrics: list[WaveMetrics],
    frames: int,
    start_index: int,
    max_jump_factor: float,
) -> list[int]:
    """
    Greedy forward-complexity path:
    - Start at a relatively simple waveform.
    - At each step, choose a higher-complexity waveform balancing:
      - similarity to current frame
      - forward motion in complexity
      - avoiding huge jumps
    """
    ordered = sorted(range(len(metrics)), key=lambda i: metrics[i].complexity)
    start_index = min(start_index, max(0, len(ordered) - 1))
    current = ordered[start_index]
    chosen = [current]
    unused = set(range(len(metrics)))
    unused.remove(current)

    complexities = np.array([m.complexity for m in metrics])
    complexity_span = float(np.max(complexities) - np.min(complexities)) + 1e-9
    target_step = complexity_span / max(frames - 1, 1)
    max_jump = target_step * max_jump_factor

    while len(chosen) < frames and unused:
        cur_complexity = metrics[current].complexity
        candidates = [
            i for i in unused
            if metrics[i].complexity >= cur_complexity
        ]

        if not candidates:
            candidates = list(unused)

        scored = []
        for i in candidates:
            delta = metrics[i].complexity - cur_complexity
            dist = frame_distance(waves[current], waves[i])
            # Penalize no progress and large jumps, but still prioritize continuity.
            progress_penalty = abs(delta - target_step) / (target_step + 1e-9)
            jump_penalty = max(0.0, (delta - max_jump) / (max_jump + 1e-9))
            score = dist + 0.18 * progress_penalty + 0.35 * jump_penalty
            scored.append((score, i))

        scored.sort(key=lambda x: x[0])
        current = scored[0][1]
        chosen.append(current)
        unused.remove(current)

    return chosen


def write_wav(path: Path, frames: list[np.ndarray], sample_rate: int = 44100) -> None:
    """Write frames as mono 32-bit float WAV — matches Vane's native saveToWav format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.concatenate(frames)
    peak = float(np.max(np.abs(data))) if len(data) else 0.0
    if peak > 0:
        data = data / peak * 0.98
    pcm = np.clip(data, -1.0, 1.0).astype("<f4")

    # IEEE float WAV (format 3): 4-byte samples, no int conversion.
    # Write RIFF header manually since Python's wave module only supports PCM.
    data_bytes = pcm.tobytes()
    data_size = len(data_bytes)
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write((36 + data_size).to_bytes(4, "little"))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write((16).to_bytes(4, "little"))          # chunk size
        f.write((3).to_bytes(2, "little"))            # format: IEEE float
        f.write((1).to_bytes(2, "little"))            # channels
        f.write(sample_rate.to_bytes(4, "little"))
        f.write((sample_rate * 4).to_bytes(4, "little"))   # byte rate
        f.write((4).to_bytes(2, "little"))            # block align
        f.write((32).to_bytes(2, "little"))           # bits per sample
        f.write(b"data")
        f.write(data_size.to_bytes(4, "little"))
        f.write(data_bytes)


def monotonicity_score(values: list[float]) -> float:
    if len(values) < 2:
        return 1.0
    diffs = np.diff(values)
    return float(np.mean(diffs >= -1e-6))


def continuity_score(distances: list[float]) -> float:
    if not distances:
        return 1.0
    # Convert mean distance into an approximate 0..1 score.
    mean_d = float(np.mean(distances))
    return float(max(0.0, min(1.0, 1.0 - mean_d)))


def iter_wavs(folder: Path) -> Iterable[Path]:
    for pattern in ("*.wav", "*.WAV"):
        yield from folder.rglob(pattern)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Vane AKWF wavetable candidates.")
    parser.add_argument("input", type=Path, help="AKWF folder or subfolder containing single-cycle WAV files.")
    parser.add_argument("--out", type=Path, default=Path("source/AKWF/candidates"), help="Output folder.")
    parser.add_argument("--metadata", type=Path, default=Path("metadata/akwf_candidates.json"), help="Metadata JSON path.")
    parser.add_argument("--frames", type=int, default=32, help="Frames per output wavetable.")
    parser.add_argument("--frame-size", type=int, default=2048, help="Samples per frame.")
    parser.add_argument("--tables", type=int, default=8, help="Number of candidate tables to build.")
    parser.add_argument("--prefix", default=None, help="Output table filename prefix. Defaults to input folder name.")
    parser.add_argument("--max-jump-factor", type=float, default=2.2, help="How much complexity jumping to tolerate.")
    parser.add_argument("--license", default="CC0", help="License metadata for source collection.")
    parser.add_argument("--source-name", default="AKWF", help="Source collection name.")
    args = parser.parse_args()

    paths = sorted(iter_wavs(args.input))
    if not paths:
        raise SystemExit(f"No WAV files found in {args.input}")

    waves: list[np.ndarray] = []
    metrics: list[WaveMetrics] = []

    for path in paths:
        try:
            raw, _sr = read_pcm_wav(path)
            frame = resample_cycle(remove_dc_and_normalize(raw), args.frame_size)
            frame = remove_dc_and_normalize(frame)
            waves.append(frame)
            metrics.append(compute_metrics(path, frame))
        except Exception as e:
            print(f"Skipping {path}: {e}")

    if len(waves) < args.frames:
        raise SystemExit(f"Only {len(waves)} readable WAV files; need at least --frames={args.frames}")

    prefix = args.prefix or args.input.name.replace(" ", "_")
    args.out.mkdir(parents=True, exist_ok=True)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)

    all_tables: list[TableMetadata] = []
    used_starts = np.linspace(0, max(0, len(waves) - args.frames), num=args.tables, dtype=int)

    for table_num, start in enumerate(used_starts, start=1):
        chosen = choose_sequence(
            waves=waves,
            metrics=metrics,
            frames=args.frames,
            start_index=int(start),
            max_jump_factor=args.max_jump_factor,
        )

        aligned_frames: list[np.ndarray] = []
        previous = None
        for idx in chosen:
            frame = waves[idx]
            if previous is not None:
                frame = align_to_reference(frame, previous)
            aligned_frames.append(frame)
            previous = frame

        distances = [
            frame_distance(aligned_frames[i], aligned_frames[i + 1])
            for i in range(len(aligned_frames) - 1)
        ]
        complexities = [metrics[i].complexity for i in chosen]
        centroids = [metrics[i].spectral_centroid for i in chosen]

        table_id = f"akwf_{prefix}_{table_num:03d}"
        wav_path = args.out / f"{table_id}.wav"
        write_wav(wav_path, aligned_frames)

        meta = TableMetadata(
            id=table_id,
            origin="assembled_from_single_cycle_sources",
            source_collection=args.source_name,
            source_folder=str(args.input),
            license=args.license,
            curation_status="candidate_unplayed",
            frame_count=len(aligned_frames),
            frame_size=args.frame_size,
            output_wav=str(wav_path),
            build_strategy="greedy_simple_to_complex_with_adjacency_similarity_and_phase_alignment",
            adjacency_distance_mean=float(np.mean(distances)) if distances else 0.0,
            adjacency_distance_max=float(np.max(distances)) if distances else 0.0,
            complexity_min=float(np.min(complexities)),
            complexity_max=float(np.max(complexities)),
            spectral_centroid_min=float(np.min(centroids)),
            spectral_centroid_max=float(np.max(centroids)),
            monotonicity_score=monotonicity_score(complexities),
            continuity_score=continuity_score(distances),
            primary_controllers=["CC02 breath", "MPE slide"],
            source_files=[metrics[i].path for i in chosen],
            notes="Candidate only. Audition with breath and slide before promoting to curated/.",
        )
        all_tables.append(meta)

    output = {
        "schema": "vane-akwf-candidate-build-v1",
        "input": str(args.input),
        "table_count": len(all_tables),
        "frame_count": args.frames,
        "frame_size": args.frame_size,
        "tables": [asdict(t) for t in all_tables],
        "source_metrics": [asdict(m) for m in metrics],
    }

    with args.metadata.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote {len(all_tables)} candidate tables to {args.out}")
    print(f"Wrote metadata to {args.metadata}")


if __name__ == "__main__":
    main()
