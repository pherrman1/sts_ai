# Wave 2: corrected-reference factorial development

The 32-pair discovery wave is complete: Fprod25wins, RestOff28, ShopFix27,
ShopOff27, Fflat26, FinalBinary26, BossOff24, SkipZero25. All256runs completed.
These outcomes select candidates only. RestOff gains3wins, with4rescues and1
regression. ShopFix gains2, with2rescues and0regressions; both rescues also occur
under RestOff. Their combination is therefore not presumed additive. ShopFix
outranks the tied ShopOff because it repairs a reproduced feature defect and
has fewer observed regressions. Fflat's1netwin costs2.28times baseline CPU;
FinalBinary changes no paired win versus Fflat. Zero observed discordance is
not equivalence. BossOff stops on negative evidence; SkipZero is inconclusive.

Optional Ruby Recall was independently reproduced despite keys-off. The common
reference now enables STS_OOC_SKIP_OPTIONAL_RECALL=1 for both V4 candidate
eligibility and random fallback. All four arms also share public8, learned-stop,
MCTSoff, Act3cutoff, keys-off, original models and the new immutable binary.
Forced-only-Recall remains legal; no game rule is relaxed. Wave1 outcomes are
never numerically reused under the changed action distribution/margin gate.

Run all four profiles Fprod, RestOff, ShopFix and RestShop on exactly fresh
610082000..610082127. RestShop combines only the two individually screened
factors. Compare each with Fprod and RestShop with each component; use exact
paired wins, discordances and the frozen 10,000-replicate percentile bootstrap.
This is development selection, not confirmatory testing. Prefer the greatest
valid number of development wins above Fprod; ties prefer one factor then
ShopFix, RestOff, RestShop. A combination has no inherited strength claim.
Independent decision-level candidates may earn a later separately frozen
comparison; final confirmation still tests exactly one champion.

128shards of4runs, rotated arm order, at most3 game processes for this wave
while one targeted REST process and two GEN2 canary processes can run. Overall
campaign limit6 game processes, OMP/BLAS1each. Measured wave1 learned-stop CPU
was12.1–14.3seconds/run;512runs project6200–7300core-seconds, roughly35–41minutes
at3workers before contention. Cap120minutes total,1800seconds per shard,
retain every failure/timeout, no replacement seeds or automatic retries.
Every invocation is guarded and records full frozen provenance and raw hashes.

Runtime gates before launch: corrected canaries for all four profiles,
default-off equality on the named old discovery run, public-capture on/off
parity, strict flag parsing and teacher-policy binding. Implementation and
scientific reviews are separate receipts. The final512-pair reserve remains
unopened. No production default or model change follows from this wave.
