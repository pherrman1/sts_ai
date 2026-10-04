# Learned Silver stopping: A/B evidence

Verdict: **`LEARNED_STOP_PASS`** under the frozen rule in [PLAN.md](PLAN.md).
See [ledger-06 §370](../../ledger-06.md).

## Provenance

- Code `ae7a6d79ed6b98963d6d5467686dcaec4815ef62` (PR #403).
- Model `gbt-b91dcfea64e1`, threshold 0.03.
- Plan commits:
  - `692da9a`: the frozen plan.
  - `885987d`: the pre-run review fixes. These changed only the plan and the
    analysis, not the binary or the model.
- Binary sha256
  `2136c77015a1546d9b538bd9603dcee377dd468b6a9f71f3b21e0b875aefa119`.
  `launch.sh` checked it before any shard started.
- Run setup:
  - Teacher [teacher.json](teacher.json).
  - Environments: [replay_env.sh](replay_env.sh) and
    [live_env.sh](live_env.sh).
  - [launch.sh](launch.sh) ran 4 shards on a 4-CPU cloud container, one CPU
    each (`taskset`), all through `tools/seed_guard.sh`.
- An independent pre-run review returned GO WITH FIXES. All three required
  fixes were applied before launch.
- One launch was stopped by the operator about 40 seconds in, before any
  seed finished: the background waiter would have killed it after 2 hours.
  Its partial outputs were set aside unread, and the launch was restarted
  detached with the same script, binary and seeds.
- Every shard of the counted launch exited 0. Wall times:
  - replay shards: 50–57 min;
  - live control: 12–15 min;
  - live learned stopping: 10–11 min.
- Training data and model are in [training/](training/).

## Files

- `run/replayK.*` are the raw `silverstopreplaygen` outputs.
  `replayK.arms.csv.gz` is gzipped, and the manifest hashes refer to the
  uncompressed file.
- `run/live_{control,learned}K.csv` with their `.meta.json` sidecars and logs
  are the raw `bestbench` outputs. `run/live_paired.txt` is the
  `paired_analysis.py` output.
- `report.json` is the full replay analysis.
- `SHA256SUMS` covers the directory.

Reproduce Part A:

```bash
cd run && for k in 0 1 2 3; do gunzip -k replay$k.arms.csv.gz; done && cd ..
python3 tools/analyze_silver_stop_replay.py run/replay0 run/replay1 run/replay2 run/replay3
```

## Part A: fight replay (primary)

96/96 sources were valid and 2,445 fights were captured. The control replay
reproduced 2,437 of them; all 8 exclusions were Smoke Bomb escapes. Neither
#199 nor learned stopping had an invalid result in any counted fight.

| Comparison, 2,437 fights | signedOutcome/fight | 95% CI | Simulation saving | CPU ratio |
|---|---|---|---|---|
| **learned − #199** | **+0.0019** | **[−0.0009, +0.0048]** | **19.4%** [18.3, 20.5] | 0.80 |
| #199 − flat 10k | −0.0029 | [−0.0054, −0.0004] | 46.4% | 0.52 |
| learned − flat 10k | −0.0010 | [−0.0040, +0.0021] | 56.8% | 0.42 |

All three gate conditions hold: S = 19.4% ≥ 10%, the CI lower bound
−0.0009 > −0.005, and there are 0 learned-only invalid fights.

By room, learned − #199:

| Room | Fights | Difference | Saving |
|---|---:|---|---:|
| NORMAL | 1,480 | +0.0010 [−0.0004, +0.0024] | 20.8% |
| ELITE | 600 | +0.0017 [−0.0030, +0.0068] | 19.5% |
| BOSS | 272 | +0.0069 [−0.0147, +0.0298] | 17.2% |
| OTHER | 85 | +0.0034 [−0.0021, +0.0108] | 16.0% |

## Part B: live paired runs (descriptive)

128 seeds `43000000..43000127`, comparing the production default (#199) with
learned stopping:

| Metric | #199 | Learned | Difference |
|---|---|---|---|
| Wins | 70.3% | 75.8% | +5.5 pp [−3.1, +14.1] |
| Mean floor | 49.1 | 48.0 | −1.1 [−2.4, +0.0] |
| Mean ending HP | 28.8 | 30.6 | +1.8 |
| CPU-seconds per run | 24.7 | 19.0 | −23% |

There were 33 discordant seeds: 13 won only with #199 and 20 won only with
learned stopping. No obvious harm appeared.

## Limits and review notes

- Most of the saving comes from the strict visit lock alone. Offline, on the
  held-out training seeds, the lock saves 38.2% against flat 10k with zero
  disagreements. The model adds about 20 pp more and causes all the observed
  action disagreements there. The runtime counter does not split lock stops
  from model stops, or fresh roots from retained roots.
- The model stops fresh roots too. Its held-out disagreement on fresh roots
  was 1.25%; #199 never stops a fresh root.
- Train vs held-out disagreement (0.06% vs 0.76%) suggests the model
  overfits. The replay outcome, not the offline disagreement, is the
  evidence that counts.
- **Inference:** with this replay variance, the gate would pass about 80% of
  the time even when the true D is 0. It is a non-inferiority result, not a
  superiority claim.
- `signedOutcome` ignores potions. The potion delta was +0.007 per fight
  (learned − #199).
- The replay starts from exact-10k source states. Part B covers the live
  trajectory effect only descriptively.
