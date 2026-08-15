# Phase-12 corrected-screen strict matched rerun

Date: 2026-08-15
Branch: `phase12-screen-contract-findings`
Baseline: `dcaf80d2129793a5f58bb89af4a018c597c14c3d`
Status: exploratory evidence; no promotion claim

## Strict contract

The existing corrected datasets passed all checks: 210,838 rows, 39,870
groups, exactly 45,088 changed rows and 7,690 changed groups, only `screen`
changed, and corrected group counts CARD/EVENT/BOSS_RELIC/UPGRADE/TREASURE/
REST/SHOP = 27,568/2,832/696/1,084/1,294/3,260/3,136. MAP was zero. Corrected
M0/M1 differed only in `labelWon`, `labelHp`, `labelFloor`, and
`labelBootstrap`.

Both retrains used exactly 40 epochs, `STRAT_PATIENCE=0`, absolute-Q, model
seed 0, the existing split, rung 4, transformer off, `STRAT_TOK_COMPILE=1`,
CUDA, and eight threads. No warm start, probes, quantiles, cross-attention,
rank loss, or objective changes were used. Python was 3.12.3, Torch
2.5.1+cu121, GPU NVIDIA GeForce RTX 3060 Ti.

## Strict training results

| Metric | Original M0 | Strict M0 | Original M1 | Strict M1 |
|---|---:|---:|---:|---:|
| Best-CE epoch | 35 | 40 | 40 | 40 |
| `val_pol_ce` | 0.508974 | 0.501773 | 0.511809 | 0.498305 |
| `policy_top1` | 0.788284 | 0.792266 | 0.790982 | 0.790982 |
| Mean margin | 5.338612 | 5.599372 | 5.709118 | 5.186920 |
| `q_top1` at selected | 0.245522 | 0.251409 | 0.250532 | 0.249154 |
| Peak `q_top1` / epoch | 0.259802 / 13 | 0.258549 / 13 | 0.253539 / 16 | 0.252036 / 15 |

The eager corrected epoch-6 anomaly disappeared under the strict compile-enabled
rerun for both arms. This does not prove compile caused the earlier behavior;
the cause of the eager/compile difference remains unresolved.

Checkpoint and native hashes:

| Artifact | SHA256 |
|---|---|
| Strict M0 `.pt` | `e600d1bfebbebb5c6b4059eb7f29dcb1c08b9a318178c43c6d77d5744f369b2e` |
| Strict M1 `.pt` | `3c98841018f5c6742238c4c192b22a6d2a35f352615e10e4f8e3941a72fd2102` |
| Strict M0 native | `97564d1be6b4f2356ef5807645a3b45126726bf8ae07cc2b7e273a860106e62a` |
| Strict M1 native | `80995be6e626b7f0278d6ac376d34718863480ef51783f20bd526f3f098c91f0` |

Both native exports passed 32-sample parity. Maximum errors were M0:
logit `2.58e-06`, value `2.26e-06`, Q `1.04e-05`; M1: logit `2.83e-06`,
value `3.06e-06`, Q `7.58e-06`.

## Strict Act-3 gameplay gate

Both strict arms used seeds `900000..900063`, 1,000 sims, 64 particles,
fair Searcher3, belief/chain off, live-valid on, VNet `models/v_combat_7k_tuned.txt`,
alpha 0.3, all strategic gates on, margin 1.0, `STS_COLLECT_KEYS=0`,
`STS_STOP_AFTER_ACT=3`, and 12 threads. Stored original M0/M1 and V4 Act-3
CSV metadata matched this runtime contract and were reused.

| Arm | Wins | Mean floor | Mean HP |
|---|---:|---:|---:|
| Strict M0 | 23/64 = 35.9% | 40.281 | 16.672 |
| Strict M1 | 16/64 = 25.0% | 37.562 | 8.672 |
| Original M0 | 17/64 = 26.6% | 38.812 | 14.562 |
| Original M1 | 16/64 = 25.0% | 38.719 | 10.312 |
| V4 | 24/64 = 37.5% | 41.797 | 20.062 |

Strict CSV hashes:

| Artifact | SHA256 |
|---|---|
| Strict M0 CSV | `56afe856fb1dafb7320065e32b22b719d9aa167f8bb1d9662c634d30fecc811e` |
| Strict M1 CSV | `991316cdcfb44d28a53a7113031f3b38fb3752d48971f0ffcbdf85b16e03a8ca` |

Repository `paired_analysis.py` deterministic bootstrap results:

| Comparison | Win delta (A-B) | 95% CI | Both win/loss | A-only/B-only | Floor delta | HP delta |
|---|---:|---|---|---|---:|---:|
| Strict M0 vs original M0 | +9.4pp | [-3.1,+21.9]pp | 11/35 | 12/6 | +1.5 | +2.1 |
| Strict M1 vs original M1 | +0.0pp | [-9.4,+9.4]pp | 11/43 | 5/5 | -1.2 | -1.6 |
| Strict M1 vs strict M0 | -10.9pp | [-25.0,+3.1]pp | 9/34 | 7/14 | -2.7 | -8.0 |
| Strict M0 vs V4 | -1.6pp | [-17.2,+14.1]pp | 11/28 | 12/13 | -1.5 | -3.4 |
| Strict M1 vs V4 | -12.5pp | [-25.0,-0.0]pp | 11/35 | 5/13 | -4.2 | -11.4 |

The paired analyzer self-test passed. The 64-seed strict M0 result recovers
approximately 9.4 of the original M0-to-V4 10.9 percentage-point gap, about
86% point-estimate recovery, but its CI crosses zero and it remains one win
below V4. Treat this as exploratory evidence, not a causal or promotion claim.

## Interpretation

Implementation correctness: the converter screen contract was wrong; corrected
datasets and strict inputs are verified.

Experimental correctness: the strict rerun changed only screen IDs relative to
the original training inputs, used compile-enabled 40-epoch training, and held
the split, model seed, objective, architecture, and gameplay settings fixed.

Scientific result: unlike the earlier eager rerun, strict corrected M0 nearly
matches V4 on this block, while strict M1 remains at the original 25.0%. This
supports the conclusion that the screen defect plausibly contributed materially
to the M0/V4 gap, but does not establish full causality. M1 is a separate null
result on this block. Coverage/source-controller distribution and other V4
differences remain unresolved.
