# Gen6 E2500 selective OOC audit, run 3: DECISION_AUDIT_MEASURED

Philipp authorized run 3 after the run-2 [Discovery root cause](../run-2/ROOT_CAUSE.md)
(“lets go with run 2 if the stuff is fixed”, 2026-10-14 22:34Z). Protocol is the
run-2 protocol with the [run-3 addendum](../PROTOCOL.md): Discovery terminal fix,
fresh seeds, nothing else changed. Run 1/2 stay invalid and are not pooled.

## Freeze and execution

- Producer `686840547577c5ff55ad77de28da4a4700c81584` (PR551 head), independent
  review PASS on that head before freeze, including a reviewer rebuild with the
  same binary hash.
- Binary `ae05716bfa3e33b58079abaed77bf21d8f5e438a9e118502403a7c3cbc39fded`,
  freeze `05187c0e4e5e8db67d2c4e2dc15e8c2f6c99f06c031e7ca169b9603fd3b3e90a`, gen6 E
  `ca9bd7f2…`, calibrated CTM manifest `00bb4da6…`. Base is the PR539 chain:
  Silver here has no ADR-0035 leaf terms and no ADR-0036 escape penalty.
- Cloud Linux container, 2 one-thread workers, `run.py prepare|canary|cohort`
  through `tools/seed_guard.sh`. Caps 200 parent / 1200 child CPU s per source.
- Canary 106000000: CANARY_VALID, 298.41 CPU s. Cohort 106000001–106000008: all
  eight returncode 0, no timeout, no failure, no retry. Largest source 688.18
  CPU s (parent 48.29, children 639.72). Total including canary 3361.62 CPU s.
- Canary and cohort reports reproduce byte-exactly from the frozen raw files.

## Result

15 roots: Act1 8, Act2 5, Act3 2 (later-act coverage adequate). Choices differ
from baseline at 9 roots for Silver8, 6 for CTM8, 5 for matched CTM.
Equal-source utility differences on the held-out plain10k reference, 5000
source-cluster bootstrap resamples, nominal 95% intervals:

| Contrast | Estimate | Interval |
| --- | ---: | --- |
| Silver8 − baseline (primary) | +0.0225 | [+0.0064, +0.0404] |
| CTM8 − baseline | +0.0014 | [−0.0156, +0.0175] |
| Matched CTM − baseline | +0.0186 | [+0.0045, +0.0371] |
| Silver8 − CTM8 | +0.0210 | [+0.0018, +0.0443] |
| Silver8 − matched CTM | +0.0038 | [−0.0026, +0.0135] |

Registered reading: directional conditional improvement of Silver8 over the
baseline choice is **shown**. A matched-CPU claim is **not resolved**: the
matched CTM arm hit its 4096-pair ceiling at 0.44–1.01× Silver cost (14 of 15
roots below 0.9), and Silver8 − matched CTM includes zero.

**Inference:** much of Silver8's edge over CTM8 looks like 8-future sampling
noise in CTM. CTM rescoring with up to 4096 futures, at roughly half of
Silver's CPU, nearly reaches Silver8. The effect sits on few roots: two roots
contribute +0.12 and +0.13, and three roots are negative.

## Limitations

Eight-source conditional pilot over two-candidate MAP choices, with nominal
intervals. The utility is the native requested-three-combat MAP-checkpoint
surrogate, not run wins; all nine source runs lost. The reference is itself
plain10k Silver, so a Silver-family selector may share its biases
(**Inference**). Pre-ADR-0035/0036 Silver. No training, default or
gameplay claim follows.

Raw outputs: `raw-evidence.tar.gz` (sha256 in `EVIDENCE.json`); binary and tar
also at `/mnt/project-files/ooc-selective-silver-audit/run-3/`.
