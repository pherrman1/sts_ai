# #401 Stage 1: grouped permutation importance for `student_sel` (OOC policy, heart1 distillation)
Analysis only (no seeds, no one_combat, no tracked files changed). Style follows §438.
## Provenance
- Artifact: `student_sel.bin` sha256 `cf6bf7fb…c507c7`; evaluated as its torch source `student.pt` `1f96f4bf…`
  (both `origin/claude/heart1-distill-data` 5a7245aa `results/E_d64_sel_xin/`; its `parity.txt`: torch vs native
  max diff 8.8e-6). ExtraInputsNN (d64, 2 layers, mult 4, 4 heads, trimmed map, `--extra-inputs`).
- Code: `tools/heart1/student_inputs.py` (main b5dd5557), silverbot `daniel-ziegler/sts_lightspeed` 84ab3ea
  (`slaythespire` built in scratch). `scripts/audit_student_sel.py` sha256 `79df0b3f…` (parity ran before a
  resume-only edit of the perm path; parity code unchanged). `scripts/make_results.py` builds results.json.
- Split: distill.py's own held-out rule, capture files with seed % 8 == 7 (whole runs, disjoint from training):
  8 old `cap-a0/a20-1080000{07,15,23,31,39,47,55,63}` (`/mnt/project-files/heart1-distill/w0{2,4,6,8}`) + 8 new
  `cap-a20-1111561{03,11,…,59}` (`data-select-20261017/w01..w08`, tar sha256 = SHA256SUMS). No TEST split exists.
- Primary metric: per-row KL(teacher softmax ‖ student softmax) over the row's choice tokens (distill.py kl_rows);
  secondary: top-1 agreement with heart1's argmax.
## Step 1 parity: PASS
- 243,103 held-out rows (log: 243,103). KL **0.05222** vs logged 0.05215 (+0.13% rel); top-1 **0.94078** vs 0.94110.
  The log used bf16 autocast on CUDA; this is fp32 CPU. Native fp32 gate.txt: old 94.03% / new 94.12% / REMOVE
  97.60%; reproduced 94.04% / 94.12% / 97.60%. All 13 per-screen KLs within 0.0004 of the log.
  Fast forward (drops all-padding token columns) vs stock forward: max diff 1.5e-8.
- Value head: **not distilled** (distill.py trains KL only). Output mean −0.027, sd 0.008 vs heart1 value mean 0.56,
  sd 0.37 (Pearson 0.46, MSE 0.486). Permutation ΔMSE ≤ 0.0006 for every group: nothing to rank.
## Scheme
- 16 groups (`results.json` `group_mapping`, silverbot input names). State groups: whole rows of the group's
  tensors (incl. sequence masks) permuted across all roots. Candidate groups (`cand:`): each root gets that
  section's candidate block from another root with the **same candidate count in that section** (roots with 0
  there untouched), so heart1's per-position targets stay aligned. `select_screen_type` (copied into every offered
  card token) belongs to the screen/select context group, not to `cand: cards offered`.
- 50,000 random held-out rows (seed 401), 5 repeats, 16 run clusters, 1,000-resample cluster bootstrap.
  Sub-features: 20,000 rows, 3 repeats; sequence sub-fields permuted among roots with equal sequence length.
  Baseline (50k): KL 0.0525 [0.0437, 0.0628], top-1 0.9412.
## Ranked groups (ΔKL, 95% cluster CI, Δtop-1, range of the 5 repeat means)
| group | ΔKL | CI | Δtop-1 | repeats |
|---|---|---|---|---|
| cand: cards offered (id, upgrades) | +5.06 | [4.69, 5.46] | −0.440 | 5.03–5.09 |
| screen/select context | +1.54 | [0.85, 2.22] | −0.176 | 1.53–1.55 |
| cand: path options | +0.482 | [0.431, 0.531] | −0.068 | 0.473–0.499 |
| cand: relics offered | +0.305 | [0.255, 0.352] | −0.032 | 0.297–0.312 |
| cand: fixed actions | +0.294 | [0.247, 0.350] | −0.039 | 0.289–0.298 |
| hp | +0.294 | [0.234, 0.357] | −0.060 | 0.291–0.299 |
| relics (held, + counters) | +0.291 | [0.206, 0.409] | −0.070 | 0.286–0.300 |
| deck (+ misc) | +0.251 | [0.222, 0.284] | −0.075 | 0.248–0.255 |
| progress (floor, act) | +0.084 | [0.069, 0.100] | −0.030 | 0.084–0.085 |
| gold | +0.055 | [0.044, 0.068] | −0.015 | 0.054–0.056 |
| cand: potions offered | +0.045 | [0.034, 0.057] | −0.006 | 0.043–0.048 |
| ascension | +0.043 | [0.034, 0.051] | −0.016 | 0.042–0.044 |
| keys | +0.039 | [0.027, 0.052] | −0.019 | 0.038–0.039 |
| potions (held) | +0.032 | [0.026, 0.039] | −0.013 | 0.031–0.033 |
| boss | +0.031 | [0.023, 0.038] | −0.015 | 0.030–0.032 |
| map (all node tokens) | +0.014 | [0.011, 0.017] | −0.008 | 0.013–0.014 |
Top features (20k): offered card ids +4.85; select_screen_type +1.40 (select rows +6.6, node rows +0.08); offered
upgrades +0.40; curHp +0.32 (maxHp +0.04); path cone+reaches_burn +0.32 (dest room +0.10, x +0.02); fixed action
enum +0.28; screen_state +0.24; relic ids +0.19; deck card ids +0.11; floor +0.081 (act +0.0007).
## Dead / near-zero (ΔKL ≤ 0.001)
- The `--extra-inputs`: deck misc −0.0000 (nonzero on only 0.03% of held-out rows: untestable here), relic counters
  +0.0001 (nonzero on 24% of rows: near-dead as trained), act +0.0007 (redundant with floor).
- Map node room types +0.0000, burning-elite flag +0.0000, map ego/reachability/agg +0.0004; toSelectCount +0.001;
  fixed-action gold +0.0008.
## Surprises and hints (**Inference** unless stated)
- Map node tokens are nearly unread (+0.014 whole block, ≈0 room types) while precomputed per-path features carry
  routing (path options +0.48, cone+burn +0.32): **removal-ablation candidate** for the map node tokens (also a
  large share of tokens, i.e. cost). Permutation does not show they are unnecessary.
- `select_screen_type` is the second-strongest input and new-data driven (Δ new +2.78 vs old +0.09): **keep**.
- Relic-counter and act inputs learned little (x_* weights small next to token embeddings): **removal-ablation
  candidates**. Deck misc needs Ritual Dagger / Genetic Algorithm coverage before judging (**missing coverage**).
- Value head is untrained in this artifact (measured). **Open question:** does any consumer read heart1's value
  from `STS_OOC_HEART1=student_sel.bin`? If so it gets a near-constant −0.03.
- Held-out runs share training's distributions (old A0/A20 trees; A20 keys-on student C runs): offline agreement,
  not play strength. Only 16 clusters, so CIs are coarse (screen context spans 0.85–2.22).
- Descriptive only: large Δ for candidate identity is expected by construction (targets are tied to the candidate at
  each position); this shows what the trained model reads, not what is necessary.
