# Hybrid logo architecture after phase 2A

> **Production update, 2026-08-22:** This document records the earlier phase-2A
> sensor architecture. The current portable production entry point is
> `comskip-final.py` / `comskip-final.exe`. It additionally contains the optional
> WeDo Movies V3 post-processing module. That module is activated only when the
> filename contains the exact, case-sensitive token `wedo-movies`; all other
> recordings bypass it. It extends detected red WeDo promotional blocks through
> the following logo-free trailer material (maximum 180 seconds) and can move a
> late logo-confirmed movie return back by at most 25 seconds when independent
> WeDo bumper, scene-cut, non-black-frame, and normal-logo-mask evidence agree.
> Corrections below five seconds are deliberately not made. The phase-2A text
> below remains as historical documentation of the underlying sensor design.

## Scope boundary

The experiment has two independent sensors, a measurement adapter, and an
offline stabilization/fusion layer. Comskip continues to make every commercial
decision exactly as before. LogoFinder is a read-only Python dependency and
produces no Comskip score.

```text
video
  +-- Comskip edge-mask sensor --> local raw CSV --+
  +-- LogoFinder crop sensor ----> dense JSONL ----+--> stabilization
                                                       +--> hybrid-logo-v1
                                                            +--> optional
                                                                 validator
```

The validator is intentionally a dead end in phase 2A: it verifies the file and
reports its coverage, but no field reaches Comskip's logo or commercial logic.

## Sensor outputs

The Comskip sensor exposes two deliberately separate layers:

- local observation: `currentGoodEdge`, local `logo_present`, and state boundaries
- film-level status: `logoPercentage` and whether the global LOGO method remained enabled

The LogoFinder sensor likewise exposes:

- local observation: crop-match score and thresholded presence at a concrete frame
- film-level learning evidence: heatmap candidate confidence, sample support, learned rectangle, and reference construction parameters

The comparison never replaces a local observation with film-level reliability. American Assassin demonstrates why: Comskip's local 37625-51374 absence remains valuable even though the 10.24% global logo coverage disables LOGO later.

## LogoFinder learning and timeline

The adapter calls LogoFinder's existing heatmap detector over samples distributed across the film. It selects the best candidate rectangle and calls LogoFinder's existing median-reference builder. Source is imported from the configured LogoFinder checkout; no implementation is copied.

After learning, only the fixed rectangle is scored against the fixed reference:

1. coarse observations approximately every second;
2. a five-part intermediate grid for intervals whose threshold state changes or whose score delta is at least 0.12;
3. frame-by-frame scoring only inside the intermediate subinterval that contains the change (or the strongest delta).

The decoder advances monotonically for nearby samples and seeks for distant refinement windows. Metadata reports requested measurements, decoder grabs, seeks, and runtimes separately.

## Reliability and local observations

Phase 2A carries two conceptually separate objects per detector:

```text
DetectorReliability
  film_quality
  supporting diagnostics

LocalObservation
  frame/time
  state: present | absent | uncertain
  local score/confidence
```

No invented numeric reliability weights are applied. Comskip's film status is
`ACCEPTED_BY_EXISTING_GATE` or `REJECTED_BY_EXISTING_GATE`, while LogoFinder is
`UNASSESSED_PHASE_2A`; raw coverage and heatmap confidence remain available as
diagnostics. Local observations are retained even when film-level reliability
is low.

Consensus should preserve four explicit outcomes:

- both present: strong logo-presence evidence;
- both absent: strong logo-absence evidence;
- Comskip present / LogoFinder absent: conflict;
- Comskip absent / LogoFinder present: conflict.

A low film-level reliability must not erase its local timeline. Conflicts remain
explicit and available for future comparison with black-frame, audio,
aspect-ratio, and other independent evidence. No scoring formula is proposed or
implemented here.

## Stabilization and alignment

LogoFinder's coarse series is median filtered, classified with a hysteresis
band, and persistence checked. Confirmed changes are backdated to the first
frame-detail pair that persistently crosses the original LogoFinder boundary.
This suppresses single-sample oscillation without moving the observable edge to
the later confirmation sample.

The canonical axis is seconds. LogoFinder frame numbers are converted with the
container FPS and matched to the nearest exported Comskip PTS within a bounded
tolerance. Frame-number equality is never assumed; the American Assassin data,
for example, commonly aligns a LogoFinder frame to a Comskip frame numbered one
higher at the same PTS.

## Suggested phase-2B boundary

Keep the detectors operationally separate. Calibrate stability and reliability
features on a labelled corpus before allowing the sidecar to challenge any
Comskip decision. Embedding Python, linking OpenCV, changing the LOGO shutdown
rule, or changing commercial scoring should wait until that calibration shows
how local confidence and film reliability behave independently.
