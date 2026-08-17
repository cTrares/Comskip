# Hybrid logo detection phase 2B report

## 1. Git state and scope

Phase 2B was performed on branch `feature/hybrid-logo-detection` at unchanged
base `1d58e8f65cc4c821d7c546064377db6dd9e38761`. The uncommitted phase-1 and
phase-2A changes were preserved. No commit, push, merge, tag, or portable build
update was made. LogoFinder remained read-only; its pre-existing untracked
database and documentation files are unchanged.

Phase 2B is a shadow experiment. Normal `cblock[].score`, block topology,
commercial classification, TXT, EDL, and every other normal output continue to
use the original Comskip path only.

Changed or added for phase 2B:

- `comskip.c`: retains validated fusion observations and optionally emits a
  separate full-precision block shadow CSV;
- `hybrid_logo_shadow.py`: equivalent offline analysis for existing verbose
  logs;
- `test_hybrid_logo_shadow.py`: parser, time-weighting, evidence, and modifier
  substitution tests;
- `README.md` and this report.

## 2. Existing LOGO intervention points

The current LOGO path is not limited to `logo_present_modifier`. The active or
configuration-dependent intervention points are:

| Area | Current code | Effect |
| --- | --- | --- |
| sensor execution | `commDetectMethod & LOGO` around lines 3720, 4367, 13298, and 15286 | controls logo sampling, finalization, allocation, and CSV reload processing |
| early give-up | around line 12466 | removes `LOGO` from `commDetectMethod` if no logo is learned in time |
| film coverage gate | lines 4632-4635 and 5288-5293 | removes `LOGO` when `logoPercentage` is outside the accepted interval |
| cutpoint validation | lines 1186 and 1586-1592 | changes removal/validation of scene-change and uniform cutpoints based on film-level logo coverage |
| AR cutpoints | line 1558 | inserts AR transitions only while LOGO is enabled (unless `cut_on_ar_change >= 2`) |
| logo transition cutpoints | lines 4420 and 4524 | optional `after_logo`/`before_logo` cutpoint insertion |
| block joining | lines 1878-1888 | `CleanLogoBlocks` joins adjacent blocks whose boundary frames both have a logo |
| AR-block joining | lines 4889-4905 | joins AR blocks when both sides have a logo |
| block logo fraction | lines 5299-5303 and 5322-5326 | calculates `cblock[i].logo`; sets it to zero when LOGO is disabled |
| score percentile | lines 5331-5336 | adjusts automatic percentile when reliable logo coverage exceeds 40% |
| direct logo scoring | lines 5625-5660 | present fraction `> logo_percentage_threshold` multiplies by `logo_present_modifier`; absent fraction below the threshold can multiply by 2 via `punish_no_logo` |
| later heuristics | lines 6198-6390 | conditional H7/H3/H4 behavior uses LOGO enablement, coverage, block logo fraction, and logo-connected blocks |
| live/on-the-fly list | lines 16712-16774 | filters black-frame commercial candidates with `CheckFramesForLogo` |

The final commercial classification itself is simply `score >
global_threshold` in `BuildCommercial`. Several logo-dependent operations occur
before that point and can therefore change either the blocks that exist or the
score entering the threshold.

This inventory explains the American Assassin failure mechanism: global logo
deactivation removes more than a score modifier. In particular, it can suppress
AR cutpoints before scoring begins.

## 3. Shadow architecture

The phase-2A sidecar is validated and retained as a diagnostic timeline. After
normal `WeighBlocks` and `BuildCommercial` have completed, phase 2B writes one
row per final normal block to
`<output-base>.hybrid-logo-shadow.csv`.

For each block it records:

- frame and PTS bounds;
- full-precision normal score, normal logo fraction/state/modifier, and normal
  classification;
- time-weighted PRESENT, ABSENT, CONFLICT, and UNKNOWN fractions;
- selected hybrid evidence and modifier;
- full-precision shadow score and hypothetical classification.

No shadow value is assigned to `cblock`, `commercial`, `commDetectMethod`, or a
normal output writer.

The controlled counterfactual replaces only the attributable logo component:

```text
shadow_score = normal_score / normal_logo_modifier * hybrid_logo_modifier
```

Thus every already-observed non-logo factor remains present. This is exact for
the multiplicative scoring chain and intentionally holds later normal branching
decisions fixed. It does not claim to simulate a second mutable `WeighBlocks`
run, because doing so could change block joins and neighbor heuristics and would
mix scoring with topology—the distinction this phase is intended to measure.

## 4. Block aggregation

Sidecar observations are integrated by elapsed PTS duration, not counted as
samples. This prevents frame-detail refinement regions from receiving more
weight than coarse one-second regions.

No film-specific threshold was added. Phase 2B reuses Comskip's existing
`logo_percentage_threshold=0.25`:

- PRESENT duration `> 0.25` -> existing `logo_present_modifier` (`0.01`);
- ABSENT duration `> 0.75`, the complement of the same threshold -> existing
  `punish_no_logo` modifier (`2.0`);
- otherwise -> neutral (`1.0`).

CONFLICT and UNKNOWN durations contribute only to their diagnostic fractions;
they cannot directly select PRESENT or ABSENT. The hybrid path is evaluated
even if Comskip's own global logo gate is off. Global reliability labels remain
diagnostic and no new numeric reliability weight is used.

## 5. American Assassin

Normal output contains 21 final blocks. The hybrid component changes five
numeric shadow scores but changes zero classifications.

### Confirmed advertising

| Ground truth | Containing normal block | Normal -> shadow | Fusion in whole block | Diagnosis |
| --- | --- | --- | --- | --- |
| 37700-51300 | 23582-63788 | 0.0001 -> 0.000001, SHOW -> SHOW | P 27.25%, A 33.61%, C 39.15%: PRESENT | B: no advertising-sized block exists |
| 86800-95600 | 63789-106561 | 0.0001 -> 0.0001, SHOW -> SHOW | P 14.86%, A 17.30%, C 67.84%: neutral | B: no advertising-sized block exists |
| 126700-136000 | 106562-140825 | 0.0001 -> 0.0001, SHOW -> SHOW | P 15.44%, A 27.16%, C 57.40%: neutral | B: no advertising-sized block exists |
| 167100-177900 | 144570-179570 | 0.0001 -> 0.0001, SHOW -> SHOW | P 5.63%, A 29.14%, C 65.23%: neutral | B: no advertising-sized block exists |

For the primary interval, the improved absence evidence is real inside the
advertising frames, but block aggregation must evaluate the existing
23582-63788 block. Its surrounding show content pushes PRESENT above the
existing 25% threshold. Hybrid logo scoring alone cannot create the missing
37700/51300 boundaries and therefore cannot repair this error.

### Confirmed non-advertising

The supplied show regions 8000-9500, 16100-18000, 22800-23800,
140700-144800, and 179300-180200 overlap several false-positive commercial
blocks in the normal output. None changes classification in shadow mode.
Conflict dominates most of these blocks and is correctly neutral. Block
17825-22816 receives PRESENT and falls from 1.0 to 0.01, but was already SHOW.

Result for American Assassin: zero of four known missed advertising intervals
and zero supplied show false positives are repaired by logo-component
substitution alone. The dominant issue is block formation, followed by
conflict-heavy fusion on oversized blocks.

## 6. Freelance

The three supplied advertising ranges exactly match existing final blocks, so
these are category A (correct topology, wrong score):

| Block/range | Fusion | Normal logo modifier | Shadow modifier | Score/classification |
| --- | --- | ---: | ---: | --- |
| 11 / 49414-56168 | 92.29% ABSENT | 2.0 | 2.0 | 0.04, SHOW -> SHOW |
| 22 / 90502-98346 | 82.98% ABSENT | 2.0 | 2.0 | 0.04, SHOW -> SHOW |
| 33 / 170046-176993 | 98.04% ABSENT | 2.0 | 2.0 | 0.04, SHOW -> SHOW |

Fusion strongly confirms what Comskip already knew locally. Because the same
`punish_no_logo` factor is already present, there is no new logo contribution.
The baseline `excessive_length_modifier=0.01` dominates and leaves every score
at 0.04. The prohibited 0.30 experiment was not used.

One unrelated 1.04-second EOF block (214720-214747) changes hypothetically from
COMMERCIAL to SHOW because its normal ABSENT modifier becomes neutral under
100% conflict. With no supplied ground truth, this is marked as a potential
regression, not an improvement.

## 7. One Day as a Lion

The confirmed advertising interval 25458-33804 has a near-exact block
25459-33830, so it is category A. Fusion is 90.83% ABSENT, but both normal and
hybrid already apply modifier 2.0. The score remains 0.04 and the block remains
SHOW. Again, the length modifier, not missing logo evidence, dominates.

The confirmed show interval 1-7198 is one block and remains correctly SHOW at
0.04. Fusion is nevertheless 100% ABSENT, demonstrating that ABSENT is not
automatically trustworthy ground truth.

For confirmed show 155184-177244, blocks 155351-167650 remain COMMERCIAL with
scores 4-9 because fusion is 100% ABSENT. Block 167651-177247 remains SHOW at
0.04. This is a local sensor/fusion failure for show content, not a global gate
failure. No supplied error is repaired.

One block outside the supplied truth, 8289-8853, changes hypothetically from
COMMERCIAL (2.0) to SHOW (1.0) because 100% conflict removes the normal
`punish_no_logo` factor. It is conservatively recorded as a potential
regression.

## 8. Good controls

### Der Koenig der Loewen 2

All 36 blocks select exactly the same normal and hybrid logo modifiers (34
ABSENT, 2 PRESENT). No score or classification changes. This is the cleanest
confirmation that the shadow path is inert when fusion agrees with Comskip.

### The Hateful Eight

Three of 84 blocks receive a different logo modifier; their scores change but
remain on the same side of 1.05. There are zero hypothetical classification
changes. Consequently no regression is observed in either good control.

## 9. Aggregate answer and error taxonomy

Across 231 final blocks:

| Film | Blocks | Modifier changes | Classification changes |
| --- | ---: | ---: | ---: |
| American Assassin | 21 | 5 | 0 |
| Freelance | 54 | 10 | 1 potential regression |
| One Day as a Lion | 36 | 3 | 1 potential regression |
| Der Koenig der Loewen 2 | 36 | 0 | 0 |
| The Hateful Eight | 84 | 3 | 0 |

None of the supplied known errors disappears solely because robust local logo
evidence is retained.

The observations separate as follows:

1. **Logo-recognition error:** One Day show 1-7198 and much of
   155184-167650 are strongly ABSENT in fusion despite being show.
2. **Fusion/aggregation limitation:** conflict-heavy oversized American
   Assassin blocks remain neutral, while the first oversized block crosses the
   existing PRESENT threshold because it includes too much surrounding show.
3. **Block-formation error:** all four American Assassin advertising intervals
   are swallowed by much larger show blocks. Hybrid scoring alone cannot repair
   them.
4. **Commercial-scoring/heuristic error:** Freelance's three exact advertising
   blocks and One Day's exact advertising block already have strong ABSENT logo
   evidence and modifier 2.0, but `excessive_length_modifier=0.01` reduces each
   to 0.04.

## 10. Output invariance and performance

For all five films, SHA-256 hashes of normal `.txt`, `.edl`, `.logo.txt`, and
`.logo-raw.csv` outputs are bit-identical to their phase-1/2A baselines.
Shadow CSV files are only 4.3-17.3 KiB.

| Film | Previous comparable run | Phase-2B wall time | Sidecar load |
| --- | ---: | ---: | ---: |
| American Assassin | 105.79 s | 106.11 s | 0.080 s |
| Freelance | 146.93 s | 145.76 s | 0.072 s |
| One Day as a Lion | 121.77 s | 122.01 s | 0.041 s |
| Der Koenig der Loewen 2 | 84.42 s | 84.67 s | 0.017 s |
| The Hateful Eight | 165.23 s | 166.45 s | 0.046 s |

The differences are consistent with run-to-run noise. Thirteen unit tests pass
and the MSYS build succeeds. Existing compiler warnings remain; no new build
error is present.

Artifacts are under
`D:\PythonProjekte\hybrid_logo_runs\phase2b_shadow_20260817`.

## 11. Phase 2C recommendation (not implemented)

The data favors option D for the American Assassin class of failures: preserve
hybrid logo evidence, but investigate block formation/cutpoint availability
before replacing the production logo score. Specifically, a future shadow-only
experiment should test whether reliable fusion transitions may propose
cutpoints while leaving scoring unchanged.

For Freelance and One Day advertising false negatives, block formation is
already adequate; a separate experiment must study the interaction between
long-block scoring and existing evidence. That should not be disguised as a
logo change.

Direct replacement (A), use only after global disable (B), or additive fusion
(C) is not justified by this corpus: it fixes none of the supplied errors and
produces two unverified classification changes. No phase-2C behavior has been
implemented.
