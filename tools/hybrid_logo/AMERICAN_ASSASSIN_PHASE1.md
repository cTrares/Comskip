# American Assassin phase-1 reference run

Run date: 2026-08-17
Video: `2026-08-07_22-25_American-Assassin_pro-7_hq.mp4`
Video metadata: 720x576, 25 fps, 214750 frames, 8590.0 seconds

Outputs were written outside the film directory and outside tracked source files:

`D:\PythonProjekte\hybrid_logo_runs\american_assassin_phase1_20260817`

## Learned LogoFinder model

- heatmap candidate: upper right
- rectangle `(left, top, right, bottom)`: `(634, 72, 667, 117)`
- candidate confidence: `0.3741292414`
- heatmap samples used: 48
- median-reference samples requested: 24
- existing LogoFinder presence threshold: `0.42`

## Timelines and first confirmed block

Comskip raw local state:

- last local-present frame: 37624
- first local-absent frame: 37625
- last local-absent frame: 51374
- first local-present frame: 51375
- final global logo percentage: `0.102446134`
- final global LOGO enabled: false

LogoFinder's refined raw threshold crossings around the same transition:

- first present-to-absent crossing: 37772 -> 37773 (1510.92 s)
- first sustained-region absent-to-present crossing: 51273 -> 51274 (2050.96 s)

The raw score can cross the threshold repeatedly near graphics and fades. These are measurements, not asserted commercial boundaries.

One-second coarse statistics:

| Region | Samples | LogoFinder present | LogoFinder score median | Comskip present |
|---|---:|---:|---:|---:|
| frames 35000-37699 | 108 | 85.19% | 0.695061 | 55.56% |
| confirmed 37700-51300 | 545 | 27.52% | 0.392675 | 0.00% |
| frames 51301-54000 | 108 | 90.74% | 0.658474 | 32.41% |

Within frames 37700-51300 the aligned coarse samples contain 395 `agree_absent` observations and 150 conflicts where LogoFinder is above threshold while Comskip remains absent. This makes the block's distribution clearly different without hiding disagreements.

## Performance

- Comskip wall time: 106.12 s
- LogoFinder heatmap learning: 1.127 s
- LogoFinder median reference: 0.435 s
- dense/refined timeline: 131.530 s
- total LogoFinder adapter: 133.807 s
- combined measured processing: approximately 239.93 s
- LogoFinder score requests: 31139 frames
- coarse output points: 8591
- decoder seeks: 2023
- decoder grabs between nearby samples: 349096

The first random-seek-only prototype run was stopped because it was unnecessarily slow; these figures are from the optimized monotonic/seek hybrid.

## Result and limitation

The acceptance signal is present: both independent sensors show a strong present/absent/present distribution around the confirmed first block, and both retain their local evidence even though Comskip globally disables LOGO. LogoFinder's boundary sampling is frame-level rather than the historical 60-second/5-second scan.

The main open issue is threshold noise: the full LogoFinder raw timeline contains many short crossings (`4059` adjacent-frame crossings in this run). Before any commercial integration, a multi-film calibration must distinguish local score, temporal persistence, an uncertainty band, and film-level detector reliability. No film-specific smoothing or commercial classification was added in phase 1.

Comskip exported 214746 internal timeline rows while OpenCV reported 214750 container frames. The tested first-block alignment is consistent, but a phase-2 sidecar reader must use PTS-aware alignment and explicitly handle tail differences, variable frame rate, and decoder frame-number differences.
