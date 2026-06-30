# Branch auto-merge automation

`.github/workflows/auto-merge-claude-branches.yml` folds every `claude/*`
branch into the integration branch automatically, so you never have to use
GitHub's "Compare & pull request" flow for them.

## What it does

On each run it:

1. Checks out the target branch **`claude/quirky-wright-uddjow`**.
2. Walks every remote branch matching `claude/*`.
3. For each branch that is ahead of the target, attempts a merge:
   - **Clean merge** → folded into the target.
   - **Conflict** → aborted and left untouched, then listed in the run summary
     so you can resolve it by hand.
4. Pushes the target once, with all clean merges from that run.
5. Deletes each branch that is now fully merged into the target (its commits
   live on in the target, so nothing is lost). Branches that conflicted are
   never deleted. Deletion only runs after the merge push succeeds.

No pull requests are opened. To merge-only and keep the source branches, set
`env.DELETE_MERGED` to `"false"` in the workflow.

## When it runs

| Trigger | Purpose |
|---------|---------|
| `schedule` (every 30 min) | Periodic sweep; catches branches pushed at any time, including ones that predate this workflow. |
| `workflow_dispatch` | Run on demand from the **Actions** tab. |
| `push` to `claude/**` | Immediate sweep — only fires for branches that already contain this workflow file. |

## Activation

`schedule` and the Actions-tab dispatch only go live once this file is on the
repository's **default branch**. Until then, either:

- merge this branch into the default branch, or
- run it manually: **Actions → Auto-merge claude branches → Run workflow**,
  selecting this branch.

## Tuning

- **Target branch** — change `env.TARGET_BRANCH` in the workflow.
- **Frequency** — change the `cron` expression.
- **Deletion** — `env.DELETE_MERGED` (`"true"` by default). Set to `"false"` to
  keep merged branches around.
- **Protected branches** — `env.PROTECTED_BRANCHES`, a space-separated list that
  is never merged and never deleted. The automation's own branch
  (`claude/branch-cleanup-automation-dc07m8`) is protected by default; add any
  work-in-progress branches you want left alone.
- **Conflicts** — conflicting branches are reported, never force-merged and
  never deleted. Resolve them manually; the next sweep picks them up once clean.
