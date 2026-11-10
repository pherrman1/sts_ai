# D2b: D2 continued on fresh seeds (Gumbel distillation, 2026-11-10)

Philipp, 2026-11-10 23:15 CET: "Kannst du auch einfach die Worjer bis morgen um 8 uhr laufen lassen für mehr Daten?"
D2 (`../README.md`, 4,096 runs) ends around 05:30 CET; D2b keeps the same 40 workers busy until about 08:00 CET.

Identical to D2 (same code 823bbad0, binary ed373563, `record_env.sh`, `run_unit.sh` apart from the seed check, queue
settings) on 1,536 fresh natural A20 seeds 111954096-111955631, 192 units of 8 (`units.txt`), share
`/mnt/project-files/gumbel-distill/d2b`. Each worker starts D2b after its own D2 wait printed FINISHED. D2 and D2b are
one data set for training (same teacher, disjoint seeds); they are verified and extracted separately.
