# RemoveLow: fixed fresh development

The complete fixed32pair discovery passed all contracts and gave RemoveLow
27wins versus Fprod26, one rescue and no regression. This satisfies the frozen
strictly-more-wins screening rule. It is adaptive discovery, not superiority.

Run exactly Fprod and RemoveLow on the previously reserved fresh sources
610082256..383 (128pairs,256totalruns). Use immutable d35b42b1 producer and
unchanged models/profile; only STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT differs.
Do not inherit or pool prior outcomes. No replacement, extension, retuning or
combination. Invalid or missing runs invalidate a clean comparison.

Use the frozen removal analyzer85f51b7d, paired10,000 bootstrap replicates,
RNG20261008. Advance only if candidate valid wins strictly exceed Fprod.
For distinct surviving candidates, exploratory nomination uses greatest
paired development gain, then lower measured CPU and earlier protocol for
ties. Comparisons on different cohorts add selection noise; only one final
frozen fresh512pair trial can establish the campaign superiority criterion.

Budget: expected3700CPU seconds, P3 (OMP/BLAS1), outer3600seconds,
shardtimeout900seconds. Start only after the fixed GEN2 tranche dispatch is
finished, so two existing development queues plusP3 plusone card canary/screen
stay within six full-game workers. Latest start06:15local; hardstop07:15local,
with outer timeout clamped to remaining deadline. This is one authorized
256run experiment despite4seedshards. Freeze all jobs before launch. Final
confirmation610083000..511 remains untouched until champion freeze.
