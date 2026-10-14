# Generation-5 self-play data: frozen configuration (2026-10-14)

Philipp 07:40Z: "Maybe do gen 5 at 20k in the same net"; workers: 8 (his card tap, 07:41Z).
Same as gen 4 (`../gen4/FROZEN.md`, same commit f73e6ad7 and binary b4586cfc) except:
- Teacher 20,000 sims, prior gen 4 (`../gen4/model/combat_policy_mlp_gen4.txt`, 3ebeab9d…52d6), 128/64.
- Seeds (coordinator): natural 94000000-94000511, perturbed 94001000-94001511; N = 8.
- Per-unit timeout `timeout --kill-after=60 9000` (gen 4 lost one lane for 1h40m+ to an endless
  `SilverSearcher::rolloutToEnd`, seed 91000228). A timed-out unit is rc 124/137, failed, not rerun.
- Smoke (seeds 74066000 natural, 74066010 perturbed, 1 run each, worker env + timeout wrapper):
  rc 0, 287 / 482 roots, 68 s / 259 s wall; manifests producer f73e6ad7, teacher
  silver-az-20000-k8-rb0-3ebeab9d. Timeout path: seed 74066020 with a 5 s limit gives rc 124,
  no leftover process.
