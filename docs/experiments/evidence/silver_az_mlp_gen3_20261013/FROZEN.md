# Generation-3 self-play data: frozen configuration (2026-10-13)

Same recipe as generation 2 (`../gen2/FROZEN.md`), with the generation-2 prior.
- Code: main `37b7d33eb1ab342eeb6fbe701b54f1d05b7d5a08` (includes #520 `silverazgen`).
- Binary: Release `one_combat`, sha256 in `BINARY_SHA256` (9098ee11…b0f7, identical to gen 2's;
  rebuilt at 37b7d33e).
- Prior: `/mnt/project-files/silver-az-mlp/gen2/model/combat_policy_mlp_gen2.txt`, sha256 7eef7ce1…a471.
- Search: flat exact 2,000 sims, MLP tree prior K = 8, weight 400, root bonus off.
- Environment: `env.sh` (as gen 2 apart from the git SHA and model file).
- Seeds (coordinator, 88M): natural 88000000-88000511, perturbed 88001000-88001511, A0.
  256 units of 4 seeds; `worker.sh W N OUT`, N in {4, 8, 16}.
- Loop guard (free-play cap) is not merged; a stalled fight (native Silver 1000-decision abort)
  is dropped in packing as in gen 2 (`pack --drop-no-fight g3`).
- Smoke: worker.sh with seeds 74053000-74053001 natural, 74053010-74053011 perturbed (1 seed per
  unit): 4/4 rc 0, manifests show producer 37b7d33e, prior 7eef7ce1, teacher
  silver-az-2000-k8-rb0-7eef7ce1.
- Outputs per worker: `wWW.tar` + `wWW.DONE.txt` in this folder.
