# Phase B.5 Real PandaLip Key Reduction A/B Evaluation

Evaluation date: 2026-08-31  
Blender: 5.1.1  
Reference scene: `PandaLip_Controller_Test.blend` (opened read-only; comparison saved separately)

## Input and conditions

- Input: `Panda-lip_Test_Voice.pandalip`
- PandaLip v1, `lpc-formant-v1`, `speech`, `japanese_neutral_v1`
- Duration: 40.832 seconds
- Samples: 4,084 at a fixed 10 ms hop
- Source keys: 20,420 (`4,084 × 5`)
- Start Frame: 0
- FPS: 24 / `fps_base=1.0`
- Target: `PandaLip`
- Face: `M_Miyuki_Face`
- Drivers: `CTRL_Lip_A/I/U/E/O` local X to `Fcl_MTH_A/I/U/E/O`
- Camera: `Camera`
- Render engine: Blender Workbench
- Audio: the existing `Panda-lip_Test_Voice.wav` Sound strip beginning at frame 0

All four modes were imported from the same validated data in one Blender process.
First/Last, Subframe timing, LINEAR interpolation, tolerance bounds, and the
actual Shape Key Driver values were checked before rendering.

The evaluation is reproducible from the repository root:

```powershell
blender --background --factory-startup PandaLip_Controller_Test.blend `
  --python tests/blender/real_data_ab_evaluation.py -- `
  Panda-lip_Test_Voice.pandalip dist/phase_b5 --render --save-blend

blender --background --factory-startup dist/phase_b5/PandaLip_PhaseB5_AB.blend `
  --python tests/blender/render_phase_b5_ab_clip.py -- `
  dist/phase_b5/clip_rapid_transition 38.4 39.4 25
```

## Aggregate results

| Mode | Tolerance | Keys | Reduction | MAE | RMS | Max error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original | Off | 20,420 | 0.000% | 2.154e-9 | 4.319e-9 | 2.979e-8 |
| High | 0.0025 | 6,584 | 67.757% | 0.0006773 | 0.0009659 | 0.0024994 |
| Middle | 0.01 | 3,086 | 84.887% | 0.0029922 | 0.0038885 | 0.0099979 |
| Low | 0.02 | 2,069 | 89.868% | 0.0053606 | 0.0070278 | 0.0199678 |

Original retained all 20,420 keys. The remaining error is Blender float storage
noise and is consistent with the Phase A reference path.

## AIUEO results

| Mode | Channel | Keys | Reduction | Max error |
| --- | --- | ---: | ---: | ---: |
| High | A | 2,099 | 48.604% | 0.0024980 |
| High | I | 996 | 75.612% | 0.0024994 |
| High | U | 1,164 | 71.499% | 0.0024990 |
| High | E | 1,579 | 61.337% | 0.0024921 |
| High | O | 746 | 81.734% | 0.0024946 |
| Middle | A | 1,016 | 75.122% | 0.0099979 |
| Middle | I | 448 | 89.030% | 0.0099571 |
| Middle | U | 549 | 86.557% | 0.0099691 |
| Middle | E | 739 | 81.905% | 0.0099720 |
| Middle | O | 334 | 91.822% | 0.0099453 |
| Low | A | 703 | 82.786% | 0.0199604 |
| Low | I | 292 | 92.850% | 0.0198327 |
| Low | U | 354 | 91.332% | 0.0199678 |
| Low | E | 491 | 87.977% | 0.0199393 |
| Low | O | 229 | 94.393% | 0.0199339 |

Every channel remained within its selected tolerance.

## Important peaks

The raw local-maximum count includes small analyzer fluctuations, so a second
measurement selected 310 visually relevant candidates using this fixed rule:

- value at least 0.1;
- prominence at least 0.05 within a 100 ms neighborhood.

| Mode | Exact source-peak key retained | Peak-center max error | Matched peak max amplitude difference | Max timing shift |
| --- | ---: | ---: | ---: | ---: |
| Original | 100.000% | 2.979e-8 | 2.979e-8 | 0 ms |
| High | 94.194% | 0.0024405 | 0.0023790 | 10 ms |
| Middle | 75.806% | 0.0099635 | 0.0068150 | 20 ms |
| Low | 83.871% | 0.0165290 | 0.0129560 | 30 ms |

An exact source key is not required to preserve a peak: an adjacent retained
LINEAR key may reproduce it within tolerance. All measured peak shifts remained
below one 24 fps frame (41.67 ms). The selected 140 ms short A pronunciation at
28.42 seconds retained the A peak at the original source time in every mode.

## Focus windows

| Feature | Time/range | High max | Middle max | Low max | Active dominant-channel match H/M/L |
| --- | --- | ---: | ---: | ---: | --- |
| Short pronunciation | 28.27–28.57 s | 0.002284 | 0.009582 | 0.019375 | 100% / 100% / 100% |
| Large opening | 22.47–22.77 s | 0.002349 | 0.009539 | 0.015153 | 100% / 100% / 100% |
| Small mouth | 13.85–14.15 s | 0.001934 | 0.008922 | 0.017469 | 100% / 100% / 100% |
| Rapid transition | 38.72–39.02 s | 0.002437 | 0.009686 | 0.019826 | 100% / 96.77% / 83.87% |
| Long vocalization | 35.31–35.96 s | 0.002462 | 0.009143 | 0.019256 | 100% / 100% / 100% |
| Zero return | 8.53–8.83 s | 0.001639 | 0.009741 | 0.018729 | 100% / 100% / 100% |
| Longest low activity | 6.32–6.56 s | 0.001759 | 0.006576 | 0.009981 | 100% / 100% / 100% |
| Continuous speech | 29.09–30.09 s | 0.002451 | 0.009978 | 0.019628 | 100% / 98.02% / 98.02% |

This recording is continuous speech and does not contain a genuinely long
silence. Its longest `max(A,I,U,E,O) <= 0.03` run is 0.24 seconds. Long-silence
behavior therefore remains additionally covered by the deterministic Phase B
synthetic regression.

## Graph Editor editability

| Mode | Total keys/s | A/I/U/E/O keys/s | Median key gap A/I/U/E/O |
| --- | ---: | --- | --- |
| Original | 500.12 | 100.02 / 100.02 / 100.02 / 100.02 / 100.02 | 10 / 10 / 10 / 10 / 10 ms |
| High | 161.25 | 51.41 / 24.39 / 28.51 / 38.67 / 18.27 | 10 / 20 / 20 / 20 / 30 ms |
| Middle | 75.58 | 24.88 / 10.97 / 13.45 / 18.10 / 8.18 | 30 / 50 / 50 / 40 / 60 ms |
| Low | 50.67 | 17.22 / 7.15 / 8.67 / 12.03 / 5.61 | 50 / 80 / 80 / 70 / 100 ms |

- Original is a dense 10 ms reference and is not practical for broad manual edits.
- High removes most secondary keys but A/E curves remain comparatively dense.
- Middle exposes phrase shapes and edit points clearly while preserving the
  reference within 0.01; it provides the strongest editing/quality balance.
- Low is the clearest graph, but its 20 ms error allowance and rapid-transition
  dominant-channel mismatch make it appropriate only when key count is the
  priority.

The generated comparison `.blend` retains all four Actions with fake users and
adds eight `B5_` timeline markers. Two SVG plots show every retained key for the
rapid-transition and continuous-speech windows.

## Character render comparison

Eight representative frames were rendered with the existing Camera and actual
AIUEO-to-Shape-Key Drivers. No clear facial-shape difference was identifiable in
the labeled static contact sheets at normal fit-to-frame inspection.

As a temporal check, mouth-region SSIM was measured over every rendered frame:

| Clip | High | Middle | Low |
| --- | ---: | ---: | ---: |
| Rapid transition, 1.04 s | 0.999789 | 0.999461 | 0.998860 |
| Continuous speech, 2.50 s | 0.999880 | 0.999441 | 0.999127 |

The supplied videos use H.264 at 24 fps with the matching source-audio segment.
SSIM is only supporting evidence; the comparison `.blend` and videos are the
artistic-review deliverables.

## Performance

| Mode | Reduction | Key generation | Total import |
| --- | ---: | ---: | ---: |
| Original | 0.0011 s | 0.0360 s | 0.0378 s |
| High | 0.0232 s | 0.0145 s | 0.0384 s |
| Middle | 0.0341 s | 0.0086 s | 0.0433 s |
| Low | 0.0474 s | 0.0061 s | 0.0540 s |

No performance optimization was made.

## Decision

- High 0.0025: retain. No visible static degradation; 100% dominant-vowel match
  in every focus window and very high temporal similarity.
- Middle 0.01: retain and treat as a future Recommended candidate. It reduces
  84.887% of keys and materially improves graph readability. The rapid window
  has a small source-grid dominant-channel difference but no clear static facial
  difference; users can inspect the supplied audio-synchronized clip.
- Low 0.02: retain as an explicit reduction-priority option. Its limitation is
  clearest at fast vowel transitions, not at large peaks or silence return.
- Original: retain as the default/reference/debug mode.
- Preset tolerances do not need adjustment from this dataset.
- No product-code bug was found. Product implementation and metadata were not changed.
- The technical Phase C gate is satisfied. Final artistic approval can be made
  by playing the supplied comparison file/videos before Controller Template work.

## Artifacts

- `../dist/phase_b5/PandaLip_PhaseB5_AB.blend`
- `../dist/phase_b5/phase_b5_real_data_report.json`
- `../dist/phase_b5/graph_rapid_transition.svg`
- `../dist/phase_b5/graph_continuous_speech.svg`
- `../dist/phase_b5/compare_rapid_transition_24fps_audio.mp4`
- `../dist/phase_b5/compare_continuous_speech_24fps_audio.mp4`
- `../dist/phase_b5/compare_*.png`
