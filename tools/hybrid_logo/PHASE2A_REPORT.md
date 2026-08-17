# Hybrid logo detection phase 2A report

## Result and scope

Phase 2A adds a generic stabilization layer, a versioned PTS-aligned sidecar,
and an optional read-only Comskip validator. It does not alter commercial
scoring, the LOGO shutdown rule, logo masks, or LogoFinder. The LogoFinder tree
was treated as read-only throughout.

The implementation consists of:

- `hybrid_logo_fusion.py`: offline stabilization, PTS alignment, explicit
  fusion, JSONL output, summary, and timing/memory diagnostics;
- `test_hybrid_logo_fusion.py`: synthetic hysteresis, persistence, refined
  boundary, PTS-offset, conflict, and unknown-state tests;
- `comskip.c`: optional `--hybrid-logo-sidecar FILE` validation. Invalid or
  missing input is ignored after a diagnostic message.

## Stabilization model

The generic defaults are:

| Parameter | Default | Purpose |
| --- | ---: | --- |
| centered median window | 3 coarse samples | suppress isolated score noise |
| absent threshold | 0.38 | strong local absence evidence |
| present threshold | 0.46 | strong local presence evidence |
| coarse persistence | 2 samples | confirm a state change |
| boundary threshold | 0.42 | preserve LogoFinder's original decision edge |
| detail persistence | 2 frames | reject a one-frame boundary crossing |
| PTS tolerance | 0.10 s | bound cross-detector alignment |

Before the first persistent observation, state is `UNKNOWN`. Once confirmed,
scores in the hysteresis band retain the current state. A single strong sample
against the current state is marked as rejected by persistence and also retains
that state. A confirmed transition is refined back to the first pair of
consecutive detail frames on the target side of 0.42.

## Sidecar contract

`hybrid-logo-v1.jsonl` starts with one metadata record and continues with
time-ordered observation records. The primary axis is `time_seconds`.

Every observation preserves:

- LogoFinder frame, PTS, raw score/evidence, median-filtered score, stabilized
  state, local confidence, sample type, and film-level heatmap confidence;
- the nearest Comskip frame and exported PTS, PTS delta, `currentGoodEdge`,
  local state and boundaries, logo percentage, and existing global-gate status;
- `PRESENT`, `ABSENT`, `CONFLICT`, or `UNKNOWN` fusion state plus a reason.

Global reliability is categorical and separate from local evidence. Comskip is
annotated from its existing gate; LogoFinder remains
`UNASSESSED_PHASE_2A`. No numeric fusion weight is invented.

The C reader validates the version, primary axis, required observation fields,
state values, non-negative monotonic time, and complete lines. It retains only
coverage/count diagnostics in this phase, so there is no path from sidecar data
to scoring.

## American Assassin

Comskip's local logo-absence interval is frame 37625 through 51374 even though
its film-level logo coverage is only 10.2446% and the existing LOGO gate is off.
The stabilized LogoFinder boundaries are:

- absent at LogoFinder frame 37773 / 1510.92 s, aligned to Comskip frame 37774;
- present at LogoFinder frame 51274 / 2050.96 s, aligned to Comskip frame 51275.

The one-frame ID difference at equal PTS demonstrates why matching is performed
on time rather than frame identity. Around the first edge, Comskip becomes
absent at 1505.00 s, producing 5.92 seconds of explicit conflict before both
detectors agree on absence. At the second edge LogoFinder becomes present first;
the conflict lasts until Comskip is present at the 2055.00 s sample.

For LogoFinder frames 37700-51300, 2,644 of 2,789 sampled observations agree on
absence and 145 are conflicts. The longest internal conflict is 17.96 seconds
(frames 45886-46335); it is preserved rather than smoothed away. Across the
whole film the generator observed 4,059 raw threshold crossings and only 127
persistent stabilized changes.

## Cross-film controls

The same defaults were used without per-film tuning:

| Film | Raw crossings | Stable changes | Longest present | Longest absent | Longest conflict |
| --- | ---: | ---: | ---: | ---: | ---: |
| American Assassin | 4,059 | 127 | 528.0 s | 324.5 s | 485.0 s |
| Freelance | 3,414 | 62 | 1,241.6 s | 281.9 s | 240.0 s |
| One Day as a Lion | 949 | 51 | 1,423.5 s | 896.4 s | 287.0 s |
| Der Koenig der Loewen 2 | 82 | 5 | 3,236.2 s | 601.6 s | 6.0 s |
| The Hateful Eight | 1,033 | 24 | 1,933.7 s | 1,078.3 s | 18.0 s |

The range from five stable changes to 127, and from six seconds to 485 seconds
of maximum conflict, shows materially different source behaviour under one
parameter set. American Assassin and Freelance remain visibly noisy; the two
most stable controls are not forced into that pattern.

Run artifacts are outside the repository under:

- `D:\PythonProjekte\hybrid_logo_runs\american_assassin_phase1_20260817`;
- `D:\PythonProjekte\hybrid_logo_runs\phase2a_controls_20260817`.

## Performance and regression

Sidecar post-processing is small relative to video analysis. Across the five
films, stabilization took 0.02-0.11 seconds and JSONL writing 0.32-1.52 seconds.
Sidecars are 5.79-26.95 MiB; traced Python peak memory was 44.04-101.81 MiB.
The C validator loaded the 31,139-observation American Assassin sidecar in
0.076 seconds.

A full American Assassin Comskip run without the sidecar decoded 216,022 frames
in 100.10 seconds; the equivalent validator run decoded them in 101.58 seconds.
The `.txt`, `.edl`, `.logo-raw.csv`, and `.logo.txt` SHA-256 hashes were
bit-identical between the phase-1 baseline, the phase-2A no-sidecar run, and the
phase-2A sidecar run. The measured runtime difference is small enough to be
normal run-to-run noise; the reader's own measured cost is 0.076 seconds.

Nine unit tests pass (four phase-1 and five phase-2A). The MSYS build completes.
Missing-sidecar fallback was exercised and continued into normal input handling.

## Phase 2B recommendation (not implemented)

Build a labelled multi-film calibration corpus and evaluate reliability
features independently from local state. Useful candidates include Comskip mask
support and fragmentation, LogoFinder candidate margin/reference edge support,
and per-detector temporal stability. Select thresholds from held-out data and
retain an explicit abstention/conflict outcome. Only after that evaluation
should a narrowly scoped experiment let hybrid evidence challenge a commercial
decision; phase 2A intentionally stops before that boundary.
