# Independent evidence review

Independent review checked the complete packet rather than relying on the generated summary. It found 17 distinct profiles, exact 32-seed cohorts (`12002000..12002031`) in every result, trace, and support file, and 544 games total. Receipt environments and parsed startup configurations match the plan. Source, executable, combat-model, fair-play, native Silver, exact-budget, and exclusion settings match.

The reviewer independently reproduced ownership, abort, simulation-attempt, early-stop budget, imagined-combat, support-reason, and continuation-reason accounting. All battle-leaf counts are zero. Independent ranking and the deterministic 200,000-resample paired bootstrap reproduce `12_rollout3` as leader: 26/32 versus 21/32 for reference, +15.625 percentage points, discordant outcomes 10/5, interval [-6.25,+37.5] percentage points. A fresh analyzer run reproduced the generated report, summary, and index byte-for-byte, and every indexed size and hash passed.

One provenance overstatement was found and corrected before publication. The runner execution-bound the executable and combat-model hashes, but not the strategic-model bytes. The final packet therefore states the narrower evidence: every arm retains the strategic-model path and successful load marker, and the plan-time hash matches the packaging-time file. This does not prove execution-time byte identity.

Review outcome after that correction: pass. The packet supports a selection-biased local discovery result only. It does not qualify current main, a default change, or a V4 comparison.
