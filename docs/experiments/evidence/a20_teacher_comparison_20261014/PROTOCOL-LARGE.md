# Prospective larger A20 teacher comparison

Authorized by the user's acceptance of the calibrated CTM / plain2k / gen6 E
prior2k shortlist, with both 10k settings on a smaller predetermined subset.
No training, runtime default promotion, or OOC gameplay A/B is included.

## Question and existing evidence

Does the pilot's preference for plain low-budget Silver persist across more
independent source runs, and does gen6 E improve controller outcomes enough to
justify its forecast discrepancy? How much does 10k buy over 2k on paired fights?
The completed v2 pilot has four source clusters, fourteen selected fights, four
alternate futures per Silver condition, and only one Act3 source. It is useful
for selecting candidates, but cannot supply precise generalized error rates.
Its CTM is uncalibrated. Its frozen raw data and exact tooling are preserved;
neither attempt1 nor attempt2 is pooled into this prospective collection.
Historical CSV features cannot substitute for the captured full combat state.

## Fixed panel and model custody

- Excluded canary: 97150901, full five-condition anchor configuration.
- Main sources: 97150910 through 97150941 inclusive, 32 fresh source runs.
- Anchors: 97150910, 97150914, 97150918, 97150922, 97150926, 97150930,
  97150934, 97150938. These eight also run both 10k conditions.
- Every source: calibrated A20 CTM, plain Silver2k, gen6 E prior Silver2k.
- Each Silver condition: 16 paired alternate combat futures. CTM: analytic
  expectation plus 32 categorical draws, unchanged from v2.
- Source and exact original-future replay: plain Silver10k, prior off, fixed V4
  OOC policy, OOC MCTS off, Ironclad A20, project-fair search.
- CTM native files: fast ae785ec2e28ceb3755fb63a71534f873ed61a069a6c2e107ef4131a788af7b6b;
  standard e338506ddf14177bec27cfe174670bd9dcac333c26b30416b9f0c76717392b0d.
  Exact calibrated embedded manifest: 00bb4da6eb9b3117feb0579356436a96f7315ea28a8f3d1f29fd10b827c254ea;
  bossSurvivalLogitShift = -0.18325317250506112. Prior pilot CTM errors are
  not attributed to this calibrated manifest.
- Exact gen6 E: ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228.
  Tree minimum visits8, prior weight400, root bonus on.

Selection and future kernel remain PROTOCOL-V2.md and ANALYSIS-CONTRACT.md:
six first chronological slots, Act1 NORMAL/ELITE/BOSS, Act2 ELITE/BOSS,
Act3 BOSS, chosen before support/outcome filtering, without replacements.
Corrected GC battle seed/six-stream redraw and paired planner/future seeds are
unchanged. Original-future control must exactly match RAW full persistent
state/RNG. Unsupported states remain in coverage accounting. No fabricated
state reconstruction, cap increase, replacement seed, retry, or extension.

## Resource and launch contract

Clean independently reviewed producer commit, Release binary, model files,
policy export, teachers, tooling and this protocol are hashed before launch.
All seed commands go through tools/seed_guard.sh, one source per process.
Maximum33 attempts, including canary. Four simultaneous one-thread workers,
1200 CPU seconds and1800 wall seconds per source; aggregate allocated CPU cap
39,600 seconds. Actual host preflight:12 available CPUs and approximately13GB
available RAM. Expected use is far below the allocation; unusually costly
fights may still exhaust the per-source cap. Canary must pass all strict
custody, replay, progress and shape checks before cohort dispatch. A process
failure stops new dispatch, drains owned running jobs, and produces a durable
INVALID_OR_INSUFFICIENT report. Partial cohorts never supply quality claims.

## Analysis fixed before collection

Main three conditions use all32 sources; five-condition anchor panel uses
only the eight predefined sources. No pooling of 10k with missing-arm sources.
Primary metric: equal-source mean HP squared forecast error (reported as
square-root RMSE). Secondary: death Brier, HP/death bias, categorical scores,
paired controller RAW HP/death/cost deltas and separate timing scopes.
An original future is one independent behavioral reference, not optimal play.
CTM and Silver controllers differ; fidelity and controller utility are distinct.

Nominal95% intervals: paired nonparametric bootstrap of source clusters,
5000 draws with analysis-only Python Random seed97150999. Each resample draws
N source indices with replacement and retains all fights/conditions of each
source; source summaries have equal weight. Interpolate sorted bootstrap
values at2.5% and97.5%; RMSE bounds are sqrt of MSE bounds. Use identical
resample indices across arms and paired differences. No fight-level iid
intervals, adaptive analysis grids, statistical winner selection, or
population/default qualification. Categorical scores have unequal Monte Carlo
precision (CTM32 versus Silver16), so remain descriptive.

Coverage is adequate for a cross-act reading only if at least12 matched source
clusters contain Act2 BOSS and at least8 contain Act3 BOSS. If unmet, report
later-act evidence limited; do not extend or substitute. Report all absent and
unsupported slots, early deaths, source policy conditioning and reference
randomness. A paired interval excluding zero is evidence of a directional
conditional difference; overlap leaves it unresolved. Teacher choice must
consider forecast fidelity, controller outcomes, coverage and CPU together.
Even a clear result only motivates a separately reviewed next experiment;
it does not authorize training or changing OOC defaults.

Knowledge impact: experiment evidence, current research status, and the maintained
opt-in dataset environment interface. No gameplay or model default change.
