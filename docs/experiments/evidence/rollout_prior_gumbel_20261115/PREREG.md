# Rollout prior on G16 targets, stage 1: offline training and root metrics (pre-registration, 2026-11-15)

Issue #1053 (Gumbel AZ loop for the rollout prior, with auxiliary heads). Philipp, project chat 2026-11-15 14:05 CET:
"sollten wir das prior netz mal auf gumbel anpassen? Gumbel 16k spielt ja besser und damit auch anders als davor,
aber wir haben das Netz nie angepasst, oder?"; 17:08 CET: one thread per issue created today, to be worked through.
Stage 1 is offline (no game seeds, no gameplay, no default change). Stage 2 (playout harness) and stage 3 (whole
runs) are proposals here and need Philipp's typed go with a worker count before they run.

## Which prior

In production G16 + mb4 (§775) one model file, g7f_E (`models/combat_policy_mlp_g7f_E.txt`, `c45dcc0a…`), plays
four roles in a boss fight:

1. **Root prior** of the Gumbel root search (top-k sampling and the logits in the improved policy).
2. **Tree prior** (K = 8) below the root.
3. **Playout policy**: in boss rooms of Acts 1-3, Shield and Spear and the Heart, every playout step plays the argmax
   of g7f_E's logits (ADR-0050 / 0056 / 0060, `RolloutConfig::prior`, `nativeSilverPolicyArgmax`).
4. **Root table** for the greedy playouts of every other fight (ADR-0046 / 0049).

Tested so far: roles 1 + 2 only. T2 (§788) replaced them with the distilled transformer and left the playouts on
g7f_E: −1.37 pp NOT_SHOWN. §773 (policy-only net as root prior): NO_GAIN. Role 3 has never been retrained since
g7f_E (2026-10-18, gen-7 window of pre-Gumbel Silver self-play at 10k-40k, visit-share targets plus distillation
from a 512/256 teacher). This stage targets **role 3 only**; roles 1, 2 and 4 stay g7f_E in every comparison.

## Why it can pay

- §798: the playout policy is a steep lever. At G16's prior-playout roots, a 32/16 student that copies g7f_E's
  playout distribution almost exactly (KL 0.023 nats) loses +0.24 Silver Q at equal simulations (1.009 vs 0.766 at
  16k), more than halving the simulations costs (P1 8k: 0.853). Greedy playouts lose +0.48.
- Same architecture and size as g7f_E means about the same CPU per prior call (6 µs, §798 stage 0; prior playouts
  are 57 % of G16's CPU, combat speed report 2026-11-14), so a quality gain is close to free. Not exactly: the
  native kernel skips inactive ReLU units, so the cost depends on the trained weights. Every candidate's native
  µs per root is measured against g7f_E on the same feature prefix (idle machine, `silverpolicymlpcheck`), and
  stage 2 measures CPU per search directly.
- On roots, the T1 transformer (validation, max-backed Q) has q_regret 1.286 and top-1 to the Gumbel pick 0.490;
  T1's earlier D1 numbers had g7f_E at 1.38. Stage 1 measures g7f_E on exactly the same rows.

**Caveat (the main risk):** playout states differ from root states (playouts run deep, follow the prior's own
argmax and never see search). A net that is better on G16 roots may not be a better playout policy. Stage 2
measures exactly this.

## Data

- D2 + D2b G16 + mb4 roots (§787), the T1 freeze (`/mnt/project-files/gumbel-distill/FREEZE-T1.txt`, sha256
  3089cacf…, 702 unit tars), re-featurized for the MLP with `tools/rollout_prior/pack_d2.py` and `one_combat
  silversynthfeatures` (main 6126315, release binary sha256 b4fad6a0…; `STS_ACTIVE_POWER_FEATURES` default 1, as
  D2 played and as g7f_E was trained).
- **Feature parity (must hold):** `tools/rollout_prior/prior_parity.py` recomputes g7f_E's softmax from the packed
  features and compares it with the root prior the game recorded. Smoke unit natural_111950000_8: 6,725 roots,
  max |Δp| 3.3e-7, 0 argmax mismatches. The merged pack is checked the same way on a sample of 50,000 roots; any
  argmax mismatch above 0.1 % of roots stops stage 1 (the states are not what g7f_E saw).
- Per edge: visits, mean Q, max-backed Q, recorded prior; per root: Gumbel pick, room, act, encounter, HP, and the
  auxiliary targets (pack_d2.py docstring).
- Splits are T1's (`split_of`, hash of the run seed): 0 = gate holdout, **not read**; 1 = validation; 2-9 =
  training. D2 seeds 111950000-111954095; stage 2 would use §797's seeds 111980000-111980255 (no overlap).

## Training (`tools/rollout_prior/train.py fit`)

g7f_E's recipe (gen-6 E, `silver_az_mlp_gen6_20261014/train-g6_E.json`) except the distillation teacher: h1 128 /
h2 64, card, encounter and monster embeddings 16, dropout 0.15, AdamW lr 1e-3 cosine to 0, wd 1e-2, batch 1,024,
25 epochs, value head weight 0.1, final checkpoint, from scratch, seed 0. Export to `combat_policy_mlp_v2` (same
layout as g7f_E); `tools/rollout_prior/export_parity.py` checks checkpoint vs artifact and artifact vs native
(`one_combat silverpolicymlpcheck`) before any stage-2 use (smoke model: 1.3e-7 and 3.0e-7, 0 argmax mismatches).

| id | target | q source | aux heads |
|---|---|---|---|
| R0 | g7f_E as recorded (no training) | | |
| V | visit shares | | |
| CQ10 | cq:10 (completed-Q policy, ADR-0043) | backed | |
| CQ30 | cq:30 | backed | |
| CQP | cq:paper (σ = 50 + max visits: ≈ the argmax at 16k) | backed | |
| CQ30m | cq:30 | mean | |
| X-Q | best of the five above | as it | + Q head (w 1) |
| X-SH | best | as it | + short-horizon / fight-end heads (w 0.5) |
| X-QSH | best | as it | both |
| X-B | best of the eight (with its heads) | as it | + 3 epochs on playout-room rows (lr 3e-4 cosine) |

σ choice ("fitted on held-out roots", issue): the cq scale is picked from {10, 30, paper} by the validation metric
below, not by CE (CE is not comparable across targets).

## Measures (validation split, final checkpoint)

Main group = **playout rooms** (boss rooms, Act-4 elites: the states whose descendants the playout prior plays).
Co-reported: all rows, each playout encounter.

- `q_regret_backed` (primary): best finalist's max-backed Q minus the max-backed Q of the net's argmax edge
  (finalists = visits ≥ half the root's maximum; rows whose argmax edge was visited), Silver score units, T1's
  definition. The playout plays the argmax, so the argmax's regret is the right root-level proxy.
- `q_regret_mean`, top-1 to the Gumbel pick, CE to the visit shares, share of unvisited argmax edges.
- Aux heads: their own losses, and whether the policy measures improve.

## Decision rules (steering only; stage 1 makes no gameplay claim)

- **Target:** the target with the lowest playout-room `q_regret_backed` among V, CQ10, CQ30, CQP, CQ30m. If two are
  within 0.01, prefer the one that also wins `q_regret_mean`.
- **Aux head group:** kept if it lowers playout-room `q_regret_backed` by more than 0.01 **and** does not raise
  `q_regret_mean` (issue: "keep a head only if it helps the main heads"). 0.01 is about 3× the seed spread T1
  measured for its generalists (0.0014-0.0042); a seed-1 rerun of the selected net checks the spread here.
- **Candidates for stage 2:** at most three: the best net, and X-B if it is better than its parent on playout rows.
  A candidate needs playout-room `q_regret_backed` below R0 (g7f_E) by more than 0.02. If no net beats R0 by that
  much: **NO_ROOT_HEADROOM**, the line stops before stage 2 (ledger entry).

## Stage 2 (proposal, needs Philipp's go)

§798's harness (`silverazgen` + `STS_AZGEN_ROLLOUT_LADDER`, the `st` arm plays a given policy MLP at every playout
step and changes nothing else) on §797's 256 games (seeds 111980000-111980255, sentinel = play identical to §797).
Arms: `asplayed:4000` (g7f_E, control) and each candidate at 4,000, the best candidate also at 16,000 (against
§797's P1 16k). Loss = played-tree max-backed Q of the best edge minus that of the arm's pick, run-clustered
bootstrap. More than one candidate needs a small research-only change so the ladder can name several student
files. Estimate ~70-100 lane-hours (§798: 137 lane-hours for seven arms incl. greedy 64k). Caveat as §798: the
reference is the g7f_E-playout tree, which favours g7f_E-like picks, so it is conservative for the candidates.

## Stage 3 and later (proposal)

Whole-run SPRT gates (ADR-0064) need a production option for a separate playout-prior model (today the playout
prior is always the root-prior model): G16 with the new playout prior vs §775's G16 (strength), and G8 with it vs
G16 (cost). Then the AZ loop: new G16 games with the new playout prior, retrain; optionally a REINFORCE fine-tune
on playout outcomes (spire-mentor). If stage 2 shows root → playout transfer fails, the alternative is training on
captured playout states labelled by short searches (DAgger-style).

## Cost

Packing: ~1 cloud CPU-hour. Training: about 25 epochs × ~7 min on 4 cloud CPU threads per run (~3 h), or ~5 min per
run on the PC GPU. No game seeds in stage 1.
