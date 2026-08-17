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
