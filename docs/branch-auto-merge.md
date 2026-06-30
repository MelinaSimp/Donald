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

Nothing is deleted — branches are merged in, not removed. No pull requests are
opened.

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
- **Conflicts** — conflicting branches are reported, never force-merged. Resolve
  them manually; the next sweep will pick them up once clean.
