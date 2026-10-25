# Prior-anchored compression: fixed offline separability audit

Accepted user handoff, 2026-10-25. Baseline current main verified with
`git ls-remote origin refs/heads/main`: `8cce22b4d5d54733330e323b3065ca687fbcbfc5`.
Historical #844 head `1322e0d97721d9ffe9e2e41dbc69d8a5acc07a01` is read-only;
inputs extracted using `git show`, with custody hashes in sources.json. No
cherry-pick, historical worktree edit or replay of whole games.

Hypothesis: the deployed ordinary prior/value can constrain compression search
while admitting the five successful skips and rejecting 326's destructive first
skip. Evaluate **only** P4 (rank <=4), P2 (best log prior minus action <=2), V5
(value within max(0.05,2 combined SE) of best); prior argmax always eligible.
Passing requires all five positives admitted AND floor-0 negative rejected.
Selection preference P4, P2, V5. No passing gate: stop
PRIOR_ANCHOR_NOT_SEPARABLE; no beam implementation or challenge games.

Offline input inventory: 18 executed skips, 5 positive, 6 thirteen-skip,
7 R1. Each matched uniquely by case/act/floor/reward offer, deck, HP and gold;
trace decision index and state stream index differ and both are retained.
Historical public records omit obs.act and obs.deck.misc. Restore act from the
state envelope; zeros only for decks without misc-bearing cards, enforced by
the native audit. Never evaluate an old record with silent act=0.

Current source deploys student_sel cf6bf7fb... as prior (ADR-0047), X2-B plus
M0 as leaf (ADR-0057). The SR head used by #853 was explicitly NOT an online
qualified default; it is not silently substituted. Main now searches only MAP
real roots at A20 (ADR-0061), so this audit scores rewards offline, without
changing real-root routing. Current CTM auto stack and unsupported-Silver
fallback are used unmodified where a transition-capable state is qualified.

Public reward projections are checked against the complete restored record
before prior inference or semantic enumeration. Their latent native state is
NOT qualified for values. Only the floor-0 Neow reward can be reconstructed
without a gameplay replay: initialize seed 111101326, enumerate the initial
Neow choices on copies, and require full public record equality. No combat or
historical trajectory is played. That root uses the existing OocParticlePlanner
root stage, P=64, depth=0, and current deployed rollout3/CTM/X2-B+M0 stack.
Remaining CRN entries are null unless retained exact snapshots become available.
Gate V5 can fail decisively from admission of the known destructive root alone;
missing positive values cannot rescue that failure. If V5 rejects that root
and positive values are unavailable, report inconclusive, never manufacture a
passing gate or authorize Stage B.

For paired CRN means, combined SE is the sample standard error of per-particle
differences to the best action. Report marginal SEs too. No threshold fitting,
resampling, retries based on outcomes, head fitting or gameplay campaign.

Resource budget: one local lane, OMP_NUM_THREADS=1, 64 particles per legal
floor-0 action; 20-minute timeout, no additional source seeds. Tools are audit
only; default gameplay/planners unchanged. Before decision-bearing evaluation,
freeze source/model/binary hashes and independently review the audit seam.
Preliminary native token scores were inspected to validate input plumbing;
all thresholds above are user supplied, not selected from those scores.

Cycle burden: count permanent cards except Powers, unconditional played-card
exhaust (simulator doesCardExhaust with upgrade state), and guaranteed unplayable Ethereal cards (Ascender's Bane, Dazed, Void, Clumsy);
add two persistent Wounds for Mark of Pain. No speculative future cards, learned
model, targeted exhaust, Corruption synergy, draw availability, or oracle use.
Record permanent size and burden before/after every enumerated action. This is
one-pass recurring mass, not a guaranteed achievable combat active-pool size.
