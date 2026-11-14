# PPO policy-gradient noise per game: G16H24 (PG16H24) vs combat B (LONG_B / LONG_C), offline (2026-11-14)

Question (Philipp, 2026-11-14 23:23 CET, "Ja starte die Messung"): does PPO of the out-of-combat net improve more per
CPU with G8 or with G16 combat in the actors? The measurable part: how noisy is one update's policy gradient per game,
and is data volume the bottleneck (favours the cheaper G8, ~1.6x games per CPU: §781 G8S 315 s vs G16 509 s per run)
or not (favours G16)?

No gameplay, no seeds, no workers. Existing trajectories only; the running learner and actors were not touched.

## Data

| set | combat | games | played and evaluated by | Heart in sample (T 1) |
|---|---|---|---|---|
| it22 | G16H24 (PG16H24 iteration 22) | 507 (39 of 40 parts) | net-0021 (bb039751..) | 35.9% |
| it23 | G16H24 (PG16H24 iteration 23) | 507 (39 of 40 parts) | net-0022 (fa000931..) | 36.5% |
| lb35 | combat B (LONG_B iteration 35) | 520 | net-0034 (01461688..) | 9.2% |
| lc419 | combat B (LONG_C iteration 419, its last) | 520 | net-0418 (b7b46a8e..) | 19.8% |

PG16H24 trajectories were copied
read-only from the store refs `ppo-xfer/pg16h24/PG16H24/traj-0022-*`, `traj-0023-*` while waiting for the learner;
LONG_B/LONG_C parts and nets were exported from the PC learner directories as refs `ppo-xfer/gn/...` (to be deleted on
the PC after this analysis). Every set is evaluated on-policy (mean |dlogp| between native and torch = 0.0000).

## Method

`gradnoise.py`: per game i, G_i = gradient of the PPO clipped surrogate summed over the game's policy decisions,
with the learner's own advantages (reward 1{Heart}, gamma 1, lambda 0.97, the net's value head, advantages normalised
over the set), no entropy and no value term. The update's policy gradient is (1/D) sum_i G_i. 6,097,922 parameters,
vectors stored as fp16. `analyze.py`: Gram matrix K_ij = G_i . G_j, raw and with an Adam-like diagonal
preconditioner (w_j = 1/sqrt(mean_i G_ij^2)). Signal |mu|^2 = sum_{i != j} K_ij / (n(n-1)) (unbiased), per-game noise
tr Sigma = sample covariance trace, noise batch size B_noise = tr Sigma / |mu|^2 (games at which noise energy equals
signal energy). `jack.py`: delete-one jackknife SE of |mu|^2 (the percentile bootstrap fields in `analysis-*.json` are
biased upward by duplicated games and are superseded by `jackknife.json`).

## Results (measured)

| set | tr Sigma raw | |mu|^2 raw (SE) | z | |mu|^2 Adam (SE) | z |
|---|---|---|---|---|---|
| it22 | 32,249 | −5.8 (5.1) | −1.14 | −715 (853) | −0.84 |
| it23 | 31,446 | −5.3 (5.7) | −0.93 | −770 (849) | −0.91 |
| G16 pooled (1,014) | 31,846 | −3.9 (2.5) | −1.54 | −475 (397) | −1.20 |
| lb35 | 44,046 | −5.6 (12.9) | −0.43 | −819 (1,488) | −0.55 |
| lc419 | 28,171 | −6.3 (3.6) | −1.76 | −673 (481) | −1.40 |
| combat B pooled (1,040) | 36,105 | −2.9 (3.7) | −0.78 | −309 (456) | −0.68 |

- **No policy-gradient signal is detectable in any set**: every |mu|^2 estimate is ≤ 0 within its noise. Random
  half-split cosines are −0.03 to −0.06 (G16) and −0.03 to −0.06 (combat B), matching the estimator.
- **Lower bounds on the noise batch size** (one-sided 95%, taking the signal as 0 + 1.645 SE, i.e. ignoring the negative
  point estimates): G16 B_noise > 7,700 games (raw) / > 9,100 (Adam); combat B > 6,000 / > 8,000. One 520-game update
  therefore has SNR ≤ ~0.07, and the cosine between an update's policy gradient and the true gradient is ≤ ~0.25: at
  least ~93% of each update's gradient energy is sampling noise.
- **Per-game noise does not depend on combat strength** in this range: tr Sigma 31.8k (G16, 36% Heart) vs 36.1k (combat
  B, 14.5% Heart; 44.0k early LONG_B, 28.2k late LONG_C); Adam metric 5.94M vs 5.97M.
- Per-game advantage sums correlate 0.97 with the Heart outcome (G16; 0.96 combat B): the per-game gradient is
  essentially ±(outcome − V) times the game's score function. Value explained variance 0.68-0.71 (G16), 0.62-0.70 (B).
- Four independent sets all give negative point estimates (Stouffer z ≈ −2.1 on the raw metric); we found no
  mechanism (the batch mean of the advantages is ≤ 0.005 sd, so the normalisation does not explain it) and treat it as
  chance or an unexplained small negative bias; it does not change the bounds' conclusion.

## Interpretation (inference)

- PPO here is deeply noise-dominated: data volume is the bottleneck. In that regime progress scales with the number of
  games (signal accumulates linearly over updates, noise only as a random walk), not with per-update quality; a smaller
  batch with more updates would not help, more games per CPU would.
- Since per-game noise is the same under combat B and G16, G8 (between them) very likely has the same per-game noise.
  Then G8's ~1.6x games per CPU are worth ~1.6x learning speed **if** the useful signal per game under G8 is about as
  large as under G16 and points the same way for G16 play. That transfer is not measurable from gradients at this
  sample size (detecting the signal itself needs ≳10,000 games).
- Consistent with LONG_B (§756: +1.4 / +3.6 / +5.5 / +6.7 pp after 50 / 100 / 150 / 200 PPO updates, ~3.4 pp per 100
  updates): after PG16H24's 18 PPO updates the expected gain at that rate is ~0.6 pp, far below one iteration's
  in-sample SE (~2.1 pp), so "no visible effect by iteration 22" is expected and is not evidence against learning.
- Larger levers than combat strength for this noise: variance reduction of the advantage (the outcome is 97% of it),
  e.g. a better critic or shaped rewards; not tested here.

Cost: ~1.3 CPU-h (cloud, 4 cores). Scripts: `gradnoise.py NET OUT TAG TRAJ...`, `analyze.py OUT TAG TAG`, `jack.py`.
