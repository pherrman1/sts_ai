# Wave3 survivors: fixed fresh development

FullHp and ShopOff each won27/32 versus corrected Fprod26/32 in the frozen
Wave3 discovery screen. Both therefore advance under its strictly-more-wins
rule. This screen is adaptive reused discovery, not confirmation.

Use the same immutable b229f3ff binary, same models and profiles, and unchanged
711c1e8a analyzer. Run Fprod, FullHp and ShopOff on every source610082128..255:
128pairs per contrast,384totalruns, all fresh reserved development. No pooling,
replacement, extension or candidate combination. Invalid/missing runs prevent
clean advancement; retain failures. Choose the candidate with most valid wins
only if strictly above Fprod; tie priority FullHp then ShopOff as preregistered.
Report paired10,000-replicate bootstrap intervals (RNG20261008) and both
discordances. This selects an exploratory champion candidate, not superiority.

Total budget is384runs, expected5500CPU seconds, at mosttwo game processes
(OMP/BLAS1), globalcampaignmaxsix. Dispatch two fixed192run lists with xargsP1.
QueueA covers610082128..191 and can start after review. QueueB covers
610082192..255 and starts only once removal's fixed discovery queue completes,
so GEN2P4 plus removalP1 plus queueAP1 stays at six, then GEN2P4 plusA/B stays
at six. This predeclared resource sequencing never depends on outcomes.
Each queue has7200second outer wallcap and1800second shardtimeout. All jobs
and controls are frozen as one authorized experiment; splitting dispatch does
not reduce the declared budget or create additional statistical experiments.

Source and implementation were independently reviewed before discovery;
strict canary and all96discovery runtime contracts passed. Review the final
manifest, job lists and budget before launching. The final512source holdout
610083000..511 remains numerically unopened until one champion, all artifacts,
fixed sample size and primary analysis are frozen. No default flip or merge.
