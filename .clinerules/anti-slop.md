# Minimal-change and anti-slop policy

The goal is not merely to make the requested behavior work.
The goal is the smallest clear maintainable change that makes it work.

## Before implementation

1. Inspect the existing implementation before creating anything new.
2. Search with Serena/RepoWise for:
   - existing helpers
   - existing abstractions
   - analogous implementations
   - duplicate functionality
3. Prefer extending or simplifying existing code over creating parallel mechanisms.
4. Do not introduce speculative abstractions for hypothetical future use.
5. Do not add compatibility layers unless compatibility is an explicit requirement.
6. State the intended minimal implementation and its non-goals.

## During implementation

Avoid:
- duplicate helpers
- forwarding wrappers with no meaningful abstraction
- one-use classes where a function suffices
- new configuration flags without a demonstrated requirement
- defensive branches for impossible states already guaranteed elsewhere
- comments that merely paraphrase the code
- parallel implementations of existing behavior
- generalized frameworks for a single current use case
- preserving failed exploratory changes

Do not optimize for number of changes made.

## After correctness is established

A passing implementation is NOT finished.

Perform a mandatory minimization pass.

Review the complete diff against the original task and ask:

1. Which changed lines are actually required?
2. Which changes came from exploratory hypotheses that are no longer relevant?
3. Can newly added logic reuse existing repository functionality?
4. Did we introduce duplicate concepts or abstractions?
5. Can any new helper/class/file/configuration option be removed?
6. Can the implementation be expressed substantially more simply?
7. Did complexity increase more than the requirement inherently demands?
8. Did unrelated cleanup accidentally enter the patch?

Prefer deletion, consolidation, and reverting unnecessary changes.

Do not change externally observable behavior during this pass.

## Final verification

After minimization:
- rerun the relevant tests
- run git diff --check
- inspect git diff --stat
- compare the final diff with the original task
- use RepoWise risk/health/change-risk where useful

The final report must include:

- behavior implemented
- tests performed
- files changed
- additions/deletions
- what was removed during minimization
- any remaining complexity increase and why it is necessary

If the implementation can be significantly smaller without losing correctness or clarity,
it is not finished.