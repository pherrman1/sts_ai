# Generation-4 self-play data: frozen configuration (2026-10-13)

Philipp (22:04Z): "if the bigger net doesn't give us anything, do a stronger teacher for 10k sims,
let it run on 4 workers for a few hours". Same recipe as generation 3 (`../gen3/FROZEN.md`) except:
- Teacher: flat exact **10,000** sims (was 2,000), gen-3 MLP tree prior
  (`../gen3/model/combat_policy_mlp_gen3.txt`, f57b7fdd…5315), K = 8, weight 400, root bonus off.
- Code: main `f73e6ad709439ceb5c39164ae07836339dd20c92` (adds #522 Silver no-progress loop guard,
  default on, so no 1000-decision stalls; #523 shop changes; #526 opt-in leaf capture).
  Binary sha256 `BINARY_SHA256` (b4586cfc…95e1).
- Seeds (coordinator): natural 91000000-91000511, perturbed 91001000-91001511; N = 4 (Philipp).
- Bigger-net check before this (offline, pack-g3, val CE fold 3): gen 3 1.2869; scratch 128/64
  1.2878; 256/128 1.2864; 512/256 1.2838 (top-1 56.3% vs 55.5%), but native cost 28.5 vs 6.4 us
  per root (4.5x), which would raise the prior's share of search CPU from ~5% to ~20%. Judged no
  worthwhile gain, so the 10k teacher goes ahead; gen-4 training may still compare 128/64 vs 512/256.
- Smoke (seeds 74061000 natural, 74061010 perturbed, 1 run each, worker binary + env): rc 0,
  376 / 382 roots, 33 s / 74 s wall, manifests producer f73e6ad7, teacher
  silver-az-10000-k8-rb0-f57b7fdd.
- Outputs per worker: `wWW.tar` + `wWW.DONE.txt` here.
