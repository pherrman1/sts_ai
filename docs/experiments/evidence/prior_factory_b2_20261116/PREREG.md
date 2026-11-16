# Prior data factory, batch 2 (issue #1053 next prior): pre-registration (2026-11-16)

**What:** the same data run as batch 1 (`../prior_factory_20261116/PREREG.md`): same code a002b841, binary 7779af6e,
`record_env.sh` and `run_unit.sh` (copied unchanged), 32 workers × 4 lanes, queue. Only the seeds and the share
directory are new.

**Authorization:** Philipp, 2026-11-16 00:46 CET (32 workers, open-ended until he says stop, hard cap 24 h); 08:46 CET
card "Fabrik trotzdem weiterlaufen lassen"; 09:17 CET card "Beides" (free the share by deleting batch 1's raw tars
except the validation seeds, after packing, and nine finished old campaign archives).

**Seeds:** 113204096-113223999 (units of 2 runs, in order), inside batch 1's registered window 113200000-113263999.
Batch 1's 1,024 never-claimed units (scattered over its block, listed missing there) are not reused.

**Storage:** no transfer off the share is possible (pushes to transfer refs are refused, 403). The author packs each
uploaded unit (`tools/rollout_prior/pack_factory.py`, npz + xz, about 0.5 MB per unit) into
`/mnt/project-files/prior-factory-b2/packed/` and then replaces the raw tar by a stub tar (the unit's manifest, log,
.done and provenance, without the .jsonl.xz; the queue only needs the file to exist). Raw tars of validation-split
seeds (`train.py::split_of` == 1) are kept whole.

**End:** `STOP_AT` = 2026-11-17 00:15 CET (24 h after batch 1's launch); `STOP` earlier on Philipp's word or when the
share's total use reaches 9.4 GB. Then: verify, pack the rest, report.
