# Vane Wavetable Library

A curated Public Domain / CC0 wavetable collection for **Vane**, optimized for playable morph trajectories rather than bulk wavetable accumulation.

Vane-oriented curation assumes morph control primarily through:

- **Breath / CC02** from windcontrollers
- **MPE Slide / Y-axis** from expressive controllers
- Other continuous controls as secondary mappings

The central design principle is that each wavetable should behave like an intentional trajectory: adjacent frames should remain related, while the table as a whole should increase in perceived intensity, brightness, density, roughness, distortion, or complexity.

## Repository goals

1. Preserve source provenance for Public Domain / CC0 materials.
2. Build Vane-native curated tables from single-cycle waveforms and existing banks.
3. Generate synthetic candidate tables, then curate them through actual performance.
4. Store enough metadata for browsing, attribution, licensing, auditioning, and future UI integration.

## Initial source buckets

```text
wavetables/source/AKWF/        # Adventure Kid Waveforms, source-preserved
wavetables/source/WaveEdit/    # CC0 WaveEdit-compatible banks and imports
wavetables/source/KimuraTaro/  # historically Public Domain material, provenance-tracked
```

## Curated output buckets

```text
wavetables/curated/harmonic_growth/
wavetables/curated/brightness/
wavetables/curated/fold/
wavetables/curated/asymmetry/
wavetables/curated/noise/
wavetables/curated/breath_morph/
wavetables/curated/mpe_slide/
```

## Generated candidates

```text
wavetables/generated/
```

Generated tables are not automatically considered part of the curated library. They begin as candidates and should be promoted only after direct listening/performance tests.

## Curation criteria

A table should be considered Vane-ready when it scores well on:

- **Local continuity**: adjacent frames interpolate smoothly or meaningfully.
- **Global trajectory**: frame order produces a clear increase in intensity or complexity.
- **Breath playability**: CC02 control feels expressive across the useful travel range.
- **MPE slide playability**: slide control produces controllable timbral movement.
- **Sweet-spot coverage**: the full morph range contains multiple useful positions, not just one isolated good frame.
- **No unpleasant discontinuities**: sudden jumps are intentional, not accidental.

## Metadata

Primary metadata files live in `metadata/`:

- `sources.json` — source collections and license/provenance notes
- `tables.schema.json` — JSON Schema for table metadata
- `tables.example.json` — example records

## Tools

The `tools/` directory contains starter scripts for analysis, generation, and source ingestion. They are deliberately conservative: they do not relicense source material and do not promote generated candidates automatically.

## License

The repository is intended for Public Domain / CC0-compatible wavetable assets only. Source-specific license evidence should be stored in `metadata/sources.json` and, when possible, mirrored as text alongside imported source folders.
