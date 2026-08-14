# RepoWise and Serena worktree routing

This repository may be opened through multiple Git worktrees in parallel.
Never assume that the original checkout is the active repository.

## Determine the active worktree

Before using Serena or RepoWise for repository-specific reasoning, determine the
current Git worktree with:

    git rev-parse --show-toplevel

Treat the returned absolute path as the authoritative active repository root for
this Cline session.

Also obtain:

    git branch --show-current
    git rev-parse HEAD

Do not infer the active worktree from the MCP server process working directory.

## Serena

Serena is configured with `--project-from-cwd`.

Before relying on Serena:

1. Check Serena's current configuration / active project.
2. Verify that Serena's active project root is exactly the same absolute path
   returned by:

       git rev-parse --show-toplevel

3. If Serena is attached to another checkout or worktree, do not use its results
   until the correct project has been activated.

## RepoWise

RepoWise runs as a workspace-level MCP server and may know about multiple
repositories or Git worktrees.

Never rely on RepoWise's implicit or default repository.

Before the first RepoWise query in a Cline session:

1. Determine the active Git root:

       git rev-parse --show-toplevel

2. Call RepoWise `list_repos`.

3. Find the RepoWise repository entry whose resolved filesystem path exactly
   matches the active Git root.

4. Record that RepoWise repository alias for the remainder of the session.

5. Pass that alias explicitly through the `repo` parameter on every RepoWise
   tool call that supports repository selection, including architecture,
   context, symbol, search, risk, health, why, dead-code, and answer queries.

6. Never use `repo="all"` for repository-specific implementation reasoning
   unless the task explicitly requires cross-repository analysis.

7. Never use RepoWise results from another sts_ai checkout or worktree as if
   they describe the active worktree.

## Missing RepoWise worktree

If `list_repos` does not contain an entry whose filesystem path exactly matches
the active Git root:

1. Do not silently fall back to another repository.
2. Do not use RepoWise's default repository.
3. Report that the active worktree is not registered/indexed in RepoWise.
4. Continue with Git, normal repository tools, and Serena where appropriate.
5. If RepoWise is materially useful for the requested task, register/index the
   active worktree using the repository's established RepoWise workspace
   procedure before relying on RepoWise conclusions.

## Cross-check

For repository-sensitive work, these must refer to the same worktree:

- `git rev-parse --show-toplevel`
- Serena active project
- RepoWise explicitly selected repository

If they disagree, Git is authoritative. Resolve the tool routing mismatch before
using Serena or RepoWise conclusions.

## Parallel Cline sessions

Each PyCharm window/worktree is an independent coding session.

A Cline session must modify, build, test, commit, and inspect only its own Git
worktree unless the task explicitly requires otherwise.

Do not switch branches in a worktree merely to inspect another parallel task.
Do not modify files in another worktree.

The shared GCP `sts-test` remote working tree is a separate shared resource and
must not be treated as worktree-isolated.
EOF
