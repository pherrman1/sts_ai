# Supplementary completed-wave health results

**PASS with diagnostic limits.** The six authorized completed reports retain exact hash/manifest/receipt bindings. All expected arm/source coverage, tree depth histogram totals, newly completed simulation denominators and effective learned/flat budget modes validate. There are zero root error strings, descent aborts, unresolved endpoints or malformed/custody failures.

| Completed report | Real decision roots | Newly completed simulations | Cycle fallback calls | Engine-stop endpoints | Turn-limit endpoints |
|---|---:|---:|---:|---:|---:|
| wave1 | 112,783 | 636,419,500 | 1,046 | 949 | 38 |
| wave2 | 220,514 | 927,014,250 | 1,734 | 8 | 0 |
| wave3 | 42,911 | 185,257,500 | 308 | 345 | 18 |
| wave4_removal | 28,234 | 122,497,750 | 204 | 344 | 7 |
| removal_development | 114,452 | 495,640,250 | 384 | 268 | 31 |
| wave5_card_rank | 27,959 | 120,033,750 | 108 | 181 | 6 |

These counts aggregate repeated arms and reused discovery sources. They are search computation counts, not independent games or evidence of win probability. Cycle counts represent intentional on-path graph fallback. Engine-stop is a positive-HP simulator loss, which can include no-damage and loop-guard termination; tree rows cannot disambiguate the cause. Turn-limit is simulator loss after turn500 and has classification priority over HP. Their presence must remain visible rather than being called ordinary sampled deaths or zero safety stops.

Removal development has one turn-limit endpoint and zero engine-stop endpoints among246,073,000 Fprod simulations; RemoveLow has30 turn-limit and268 engine-stop endpoints among249,567,250 simulations. Both have zero root errors, aborts and nonterminal endpoints. These finite sample counts do not by themselves show broken real runs or justify a new post hoc quality threshold. All affected raw root locators are retained in the individual health reports.

The independently reproduced removal development result remains106/128 versus104/128, gain+1.5625pp,95%paired interval[-3.90625,+7.03125]; CardWinRank discovery remains22/32 versus26/32, gain-12.5pp, interval[-34.375,+9.375]. Neither is a confirmed improvement. Runtime-health review does not promote an inconclusive development result or reopen a failed discovery screen.

Reproduction: use `audit_fullrun_health.py REPORT --report-sha256 HASH --out NEW_PATH`; each `*_health_invocation.json` contains the exact executed command, report/auditor/output/log hashes and producer semantic fragment checks. The script refuses overwrite. The machine summary `completed_wave_health_summary.json` binds all six reports. Sixteen synthetic fixtures and independent strategy source review passed before real application. Frozen efficacy analyzers and raw outputs are unchanged.

The original ongoing Wave3 development and protected confirmation/TEST remained unopened by this audit. Later cohorts require a completed report and coordinator authorization; no directory discovery or partial-result pooling occurs.
