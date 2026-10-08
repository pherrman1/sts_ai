# Independent prospective diagnostic review

Integrity independently reviewed `GEN2_POST_PRIMARY_DIAGNOSTICS.md` at SHA256 `835cb0d121de3854b245c4ed5f20f5edc577b3a0e7bf6a600ccf44855e5ca401` and returned scientific PASS. The review was performed before any tranche numerical analysis by the reviewer or author.

The following implementation clarifications bind the eventual exploratory analysis without changing the frozen primary:

- Valid no-state sources contribute zero only to **effect/increment** summaries. Calibration, Brier score, reliability and dispersion are undefined for those sources: use exposed-source denominators, never inject a perfect zero error.
- Reliability bins preserve source/state/option weights, normalized within each occupied bin. Report weighted mass plus raw row and source counts. Empty bins are reported empty, never filled or dropped silently.

Primary selection/evaluation completion and custody gates remain prerequisites. This design authorizes no additional simulation, training, reselection or change to the primary conclusion.
