# HANDOFF

> Written 2026-06-25. **This documents a fresh, empty repository.** No feature
> work has happened yet. The next session is starting from zero, not picking up
> mid-stream. Most sections below are intentionally empty because there is
> genuinely nothing to hand off — that absence is the signal, not an omission.

## 1. Mission

Not yet defined. The repository (`Donald`, GitHub: `melinasimp/donald`) contains
only a placeholder README. No product or feature direction has been established
in any prior session. **The next session's real first job is to get the actual
task/goal from the user.**

## 2. Current State

Ground truth as of `git status` / `git log` on 2026-06-25:

- **Branch:** `claude/keen-euler-mkxx2d` (matches the designated dev branch; also exists on `origin`).
- **Commits:** one — `c227fe2 Initial commit: add README`.
- **Working tree:** clean.
- **Files:** `README.md` only (2 lines: a `# Donald` heading and "Project repository.").
- **Working / verified:** nothing built — nothing to verify.
- **Half-built:** nothing.
- **Broken / blocked:** nothing broken; blocked only on having a defined task.
- **Exact next action:** ask the user what they want built. Do not scaffold,
  pick a stack, or write code before that answer — there is no information to
  infer it from.

## 3. Decisions Made (and Why)

None. No technical or product decisions have been made in any session.

## 4. Architecture & Key Files

No architecture exists.

- `README.md` — placeholder, auto-generated content. Safe to overwrite once the
  project's actual purpose is known.

## 5. Gotchas & Hard-Won Knowledge

None accumulated yet.

## 6. Conventions In Play

None established. No `CLAUDE.md`, `design-principles.md`, linter config, test
setup, or build tooling exists. Conventions should be set when the first real
code lands and the stack is chosen.

Branch/process constraints carried from the task setup (these DO apply):
- Develop on branch `claude/keen-euler-mkxx2d`.
- Push with `git push -u origin claude/keen-euler-mkxx2d`.
- Do **not** open a pull request unless the user explicitly asks.
- GitHub access is scoped to `melinasimp/donald`.

## 7. Open Questions

1. **What is this project?** What should `Donald` actually do or be?
2. **What stack/language?** No constraints exist yet — needs user input.
3. **What is the first deliverable** the user wants to see?

## 8. Do Not Touch

Nothing is settled, so nothing is off-limits — except the process constraints in
Section 6 (branch name, no-PR-without-asking, repo scope), which were set by the
task configuration and should not be changed without explicit user permission.

## 9. Resume Command

> "Read HANDOFF.md. The repo is empty — there is no prior work. Ask me what I
> want to build before writing any code or choosing a stack. Develop on
> `claude/keen-euler-mkxx2d` and don't open a PR unless I ask."
