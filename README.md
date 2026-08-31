# Comskip – Enhanced Logo Detection Fork

> V4 development branch: commercial recordings listed in
> `Makromodus-Sender.txt` use the new dynamic-logo macro path. The complete
> legacy workflow remains available through `--full-analysis`. See
> `docs/V4_MAKROMODUS_PLAN.md` for the isolated V4 plan.

This repository is a custom Comskip fork focused on improving commercial detection in **raw, untrimmed TV recordings**.

The central issue addressed by this fork is not that Comskip's local logo matcher is inherently poor. In testing, the existing edge-based matcher was often very accurate once it had learned the correct station logo.

The weak point was **logo initialization**.

Raw TV recordings often begin or end with material that does not belong to the intended program: the end of the previous show, news, trailers, commercials, a different aspect ratio, the same station logo at a different screen position, no station logo at all, or the beginning of the following program.

If logo learning is based too heavily on this material, Comskip can initialize the wrong logo model and later make poor commercial decisions even though its local matcher itself is capable of good results.

This fork changes that architecture.

## Comskip V3: fast boundary mode for ad-free public broadcasters

V3 adds a separate, deliberately short path for configured public broadcasters.
It does not search for commercial blocks inside the programme. It starts from a
middle anchor, learns any useful overlay dynamically for the current recording
(without a stored logo position), scans only reduced reference regions at both
edges and writes exactly two editable blocks:

```text
frame 1 -> estimated programme start
estimated programme end -> last frame
```

The configured stations live in `Schnellmodus-Sender.txt` beside
`comskip-final.exe`. The file also contains the editing instructions: use M/N to
jump between boundaries, E to correct the end of the first block and B to
correct the beginning of the last block. The console, log, diagnostic JSON,
sidecar marker and ComskipGUI window title identify this mode as
`SCHNELLMODUS`. If the station file is absent, the automatic fast mode is
disabled; `--full-analysis` bypasses it for one recording.

## Main changes

### 1. Six-minute learning exclusion at both ends

The **first six minutes** and **last six minutes** of a recording are excluded from station-logo learning.

They are **not excluded from commercial detection**.

After logo initialization is complete, the **entire recording from the first frame to the last frame** is analyzed.

```text
Recording
|------|--------------------------------------------|------|
0:00   6:00                                      -6:00   END

       <--------- logo learning allowed --------->

<------------- complete recording analyzed ------------->
```

This rule is intentional and optimized for raw TV recordings with lead-in and lead-out material.

### 2. Multi-window Comskip logo learning

Comskip's existing fast edge-mask logo detector is retained.

Instead of treating one early learning period as authoritative, this fork learns logo candidates from **five separate windows** distributed across the valid middle section of the recording.

The candidates are compared and the **recurring logo mask** is selected. The masks are not blindly merged.

The goal is simple: learn the station logo that repeatedly appears across the actual recording, rather than trusting whatever happens to be visible near the beginning.

### 3. Local logo evidence is retained

A poor global logo percentage no longer automatically means that all useful local logo information should be discarded.

Global logo statistics can still be treated as reliability information, but a valid local logo signal remains available to the commercial detector.

### 4. Independent second logo sensor

This fork contains an additional, independent logo sensor using a different recognition strategy from Comskip's traditional edge-mask detector.

The additional sensor uses concepts including distributed sampling, stable corner-region detection, edge-frequency / heatmap analysis, reference construction from multiple samples, local similarity / correlation, temporal stabilization and PTS-based alignment.

The purpose of the second sensor is not to replace Comskip's edge matcher, but to provide an independent signal with different failure modes.

## Relationship to AdFinder

The additional logo-detection work was informed by a separate private project called **AdFinder**.

AdFinder has a different purpose: it scans already edited video files to detect commercial breaks that may accidentally have remained after cutting.

**AdFinder itself is not included in this repository, was not modified as part of this work, and is not a runtime dependency of this Comskip fork.**

The functionality required by this fork has its own implementation inside the Comskip project. You do not need AdFinder in order to use this fork.

### 5. Both logo sensors use the same safe learning region

Both logo systems follow the same initialization rule:

```text
first 6 minutes      -> do not learn
middle of recording  -> learn
last 6 minutes       -> do not learn
```

After initialization, both can analyze the complete recording, including the beginning and end.

### 6. Existing Comskip detection remains important

This is **not** a logo-only commercial detector.

After the improved logo stage, Comskip's existing detection and block-processing logic continues to run, including the mechanisms enabled by the current configuration such as black frames, aspect-ratio changes, resolution changes and existing commercial/block heuristics.

Practical testing showed that this second stage matters. The logo-only intermediate result was not always sufficient, while the final Comskip result was substantially better.

```text
better logo initialization
        +
Comskip edge-based logo detector
        +
independent second logo sensor
        +
retained local logo evidence
        +
existing Comskip detectors and block logic
        =
final commercial detection
```

### 7. Optional WeDo Movies module

The portable workflow contains an additional station-specific pass for recordings whose filename contains the exact, case-sensitive token `wedo-movies`.

Only those files use the WeDo Movies module. Every other recording bypasses it and continues through the normal Comskip pipeline unchanged.

For matching recordings, the module detects the stable red WeDo promotional layout, follows the adjoining logo-free trailer material for at most 180 seconds, and ends the commercial block when the normal movie logo is found again. If that logo is recognized late, a conservative lookback of at most 25 seconds may restore the earlier movie start. The correction is accepted only with corroborating WeDo bumper and scene-transition evidence; differences below five seconds are intentionally left unchanged.

The portable workflow also supports selective reanalysis of one previously processed film. Its former analysis and CROP/MANUELL decision are backed up before the new run.

## Why this can make a large difference

A raw recording may start several minutes before the intended movie. The preceding material can use a different aspect ratio and place the same broadcaster logo at a different vertical position.

A detector that learns immediately from the beginning can therefore build a perfectly valid model for the **wrong program geometry**.

The local matcher may not be defective at all. The initialization was wrong.

This fork changes the question from:

> What logo do I see near the beginning?

into:

> What station-logo structure repeatedly appears across several independent parts of the recording?

## Practical validation

Development was tested against several real raw TV recordings with different broadcasters, logo positions, aspect ratios and failure modes.

The final implementation was manually inspected in ComskipGUI on:

- American Assassin
- Freelance
- One Day as a Lion
- Der König der Löwen 2 – Simbas Königreich
- The Hateful Eight

The final-stage output of the completed implementation was manually judged correct on this reference set.

American Assassin was additionally rerun after finalization and reproduced the previously approved final commercial output exactly.

This is practical validation of the intended use case, **not a claim of universal 100% accuracy**.

## Intended use

This fork is primarily intended for **raw / untrimmed television recordings**, especially recordings containing several minutes of material before or after the intended movie or program.

It is particularly useful when the broadcaster keeps a stable station logo during the program and removes it during commercial breaks.

## Assumptions and limitations

The six-minute exclusion is a deliberate domain assumption.

It may be unnecessary or less suitable for:

- very short recordings
- already precisely trimmed recordings
- programs with very little usable middle section
- broadcasters that frequently remove or animate the station logo
- broadcasts where the logo repeatedly changes position
- recordings where no stable station logo exists

The current implementation should therefore be understood as an optimization for unattended TV recordings with safety margins before and after the intended program.

## Stable reference version

```text
branch: custom
tag:    custom-2026-08-31-v4-stable
```

To restore this exact source revision:

```bash
git clone <repository-url>
cd <repository-directory>
git checkout custom-2026-08-31-v4-stable
```

The stable tag is the preferred reference.

## Windows executables

The finalized portable build contains:

```text
comskip.exe
ComskipGUI.exe
comskip-final.exe
```

`comskip-final.exe` contains the runtime required by the internal second logo sensor. It does **not** require the external AdFinder project.

### SHA-256 – finalized build

```text
comskip.exe
5E6634AA97F3F5C4BF01614114F32C1B7406E3F188C273FB4B3E70A36B2F5319

ComskipGUI.exe
A92D4D6114789D61A220A6D7137822A89D4B92C4274C5257921B78DCFF0253A6

comskip-final.exe
F653870281A5CBE2ABC06728114426D2E6AB121AB4AC380F8D9686C8A59B8267
```

## GUI navigation change

```text
Down Arrow  -> +1 second
Up Arrow    -> -1 second
Page Down   -> +20 seconds
Page Up     -> -20 seconds
```

The key direction now follows the timeline consistently.

## Reproducible build

The source code for the final implementation is contained in this Comskip repository and does not depend on the external AdFinder repository at runtime.

Fresh-clone requirements, pinned Python dependencies and the complete Windows
build/package command are documented in [`BUILDING.md`](BUILDING.md). On
Windows, `.\tools\build_windows.ps1` builds the native programs, runs the
Python tests, creates `comskip-final.exe` and assembles the portable runtime
under `dist\ComSkip`.

## Development history

The final result was not produced by changing one threshold.

Several hypotheses were tested separately, including commercial-length scoring, preservation of local logo information, independent logo detection, logo-signal fusion and alternative logo initialization strategies.

The largest practical improvement appeared after changing **how the station logo is initialized** and then allowing Comskip's existing detectors to continue refining the result.

```text
exclude unreliable recording edges from learning
+
learn from multiple independent windows
+
retain local logo evidence
+
use an independent second detector
+
run the existing Comskip detection logic afterwards
```

## Relationship to upstream Comskip

This is a custom Comskip fork.

The changes address a specific weakness observed with raw TV recordings where the beginning and end of the file may not represent the intended program.

It should not be interpreted as a claim that every recording, broadcaster or workflow will always perform better than upstream Comskip. Users should compare the results against upstream Comskip on their own source material.

## License and redistribution

This fork remains subject to the applicable license terms of the original Comskip project and any third-party components distributed with the resulting binaries.

Before distributing prebuilt binaries, verify the redistribution requirements for all bundled dependencies used by the final package.
