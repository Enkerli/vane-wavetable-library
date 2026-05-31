# Vane Wavetable Curation Protocol

## Core question

Does this wavetable feel playable when morph is controlled by breath or MPE slide?

Visual appeal and spectral novelty are secondary. Vane tables should reward embodied control.

## Primary controller tests

### Breath / CC02

Use a windcontroller or breath controller with CC02 mapped to Vane morph.

Evaluate:

- Can soft breath remain musically stable?
- Does increasing breath create a convincing increase in intensity?
- Are there unwanted jumps in the middle of the breath range?
- Does the top range become expressive rather than merely harsh?
- Does the table support phrasing, swells, attacks, and decays?

### MPE Slide

Use an MPE controller with slide/Y-axis mapped to Vane morph.

Evaluate:

- Does vertical finger movement produce legible timbral control?
- Are small slide movements meaningful without being twitchy?
- Does the table support per-note expressivity?
- Are there clear regions for soft, medium, and intense states?

## Rating dimensions

Use 0–10 scores.

| Dimension | Meaning |
|---|---|
| breathCC02 | Playability with breath mapped to morph |
| mpeSlide | Playability with MPE slide mapped to morph |
| slowMorph | Quality of gradual timbral travel |
| fastMorph | Quality under fast gestures |
| sweetSpotCoverage | How much of the morph range is musically useful |

## Promotion rule

A table may move from `candidate` to `curated` when:

- License/provenance is clear.
- Breath or MPE slide has been tested.
- Sweet-spot coverage is at least 7/10.
- There are no accidental discontinuities.
- Metadata is complete enough for browsing and future UI use.

## Rejection is useful

Rejected tables should remain documented when they teach something:

- Too discontinuous
- Too static
- Too harsh too soon
- Only one good frame
- Good visually, poor under breath
- Good as sample material, poor as morph trajectory
