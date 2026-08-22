# Final recurring-logo workflow

This directory contains the released custom-Comskip logo workflow and its
historical diagnostic tools. The production entry point is `comskip_final.py`;
the Portable build packages it as `comskip-final.exe`.

## Production data flow

1. Skip the first and last six minutes for learning.
2. Learn five separate Comskip edge-mask candidates in non-overlapping windows.
3. Select a recurring candidate without merging masks or forcing an unrelated
   single candidate.
4. Run Comskip's local edge matching over the complete recording.
5. Learn the independent internal sensor from distributed middle-region
   samples using a heatmap region, median reference, and correlation score.
6. Run that sensor over the complete recording, stabilize it in time, align it
   by PTS, and preserve `PRESENT`, `ABSENT`, `CONFLICT`, and `UNKNOWN` states.
7. Feed the fused local logo evidence into the otherwise unchanged Comskip
   block/commercial processing.

## WeDo Movies module

Recordings whose filename contains the exact, case-sensitive token
`wedo-movies` receive one additional station-specific pass. No other filename
can activate this module. The console explicitly reports the selected station
profile.

The detector scans a low-resolution one-frame-per-second stream for the stable
red promo layout used during WeDo Movies breaks. A candidate must persist as an
approximately two-minute sequence with only the short, expected ident gaps;
isolated red film scenes are rejected. In active mode these high-confidence
intervals are merged with, rather than substituted for, the normal Comskip
result. `--wedo-movies-mode shadow` records the evidence without changing the
cut list, and `--wedo-movies-mode off` disables the module.

After each confirmed red block, the WeDo-specific tail extension examines at
most the following 180 seconds. It reuses Comskip's selected recurring normal
station-logo mask and extends the commercial interval until the first local
`PRESENT` observation. No additional multi-second hold is required after that
first return, so a cloud or other difficult background immediately afterwards
cannot reopen the commercial. If the normal-logo sensor was rejected as
unreliable, the tail extension is skipped rather than extending blindly.

Because the translucent normal logo can become detectable late over clouds,
grass, or similarly difficult backgrounds, the module also performs a strictly
conservative 25-second lookback. It refines the boundary only when a centered
red/white WeDo self-promo bumper cuts directly to a non-black movie frame.
The correction must recover at least five seconds and the automatically learned
normal-logo edge mask must already be strongly present on the first movie frame.
Arbitrary scene changes are never sufficient. Without all of those confirmations,
the logo-confirmed boundary remains unchanged.

The template in `WeDoMovies Modul/5.png` is retained as reference material for
a possible secondary logo confirmation. It is deliberately not required by
the primary detector because logo position and transparency vary with the
background, while the full promo layout and its duration are substantially
more stable.

The second sensor is implemented by `internal_logo_sensor.py` inside this
repository. Production has no import, path, database, executable, or repository
dependency on the external LogoFinder project. OpenCV and NumPy are bundled in
the Portable `comskip-final.exe`.

## Normal use

In the Portable directory:

```powershell
.\comskip-final.exe 'C:\path\recording.mp4'
```

The launcher creates the normal `.txt`, `.edl`, `.log`, and `.logo.txt` files
beside the recording. Temporary learning and sensor files are removed after a
successful run and retained with their path printed after a failure.

The released C behavior is selected automatically when a recurring `--logo`
mask and a valid internal `--hybrid-logo-sidecar` are supplied. Users do not
combine experimental mode switches.

## Diagnostics

`--logo-raw` writes `<output-base>.logo-raw.csv` with frame/PTS,
`currentGoodEdge`, local presence, local state boundaries, global percentage,
and global reliability. Historical phase scripts and reports remain available
for regression diagnosis; they are not required by the Portable runtime.

## Tests

```powershell
Set-Location .\tools\hybrid_logo
python -m unittest discover -v
```

`tools/review_navigation_test.c` separately verifies GUI vertical navigation:
Down/Page Down advance, Up/Page Up rewind, the original one-second/twenty-second
steps remain intact, and both ends are clamped to valid frames.
