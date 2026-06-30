#!/usr/bin/env bash
#
# Install the Donald self-knowledge pre-commit hook.
#
# The hook refreshes context/self/donald.md from the codebase on every
# commit and stages the result. It is local-only and never makes network
# calls, so it stays sub-second on a warm import.
#
# Idempotent: re-running overwrites our own previous hook in place (no
# duplication). Refuses to clobber a foreign pre-commit hook unless
# called with --force.
set -euo pipefail

FORCE=0
if [ "${1:-}" = "--force" ]; then
  FORCE=1
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
HOOK_DIR="$REPO_ROOT/.git/hooks"
HOOK="$HOOK_DIR/pre-commit"
MARKER="donald self-knowledge hook"

mkdir -p "$HOOK_DIR"

if [ -f "$HOOK" ] && ! grep -q "$MARKER" "$HOOK"; then
  if [ "$FORCE" -ne 1 ]; then
    echo "Refusing to overwrite an existing foreign pre-commit hook:" >&2
    echo "  $HOOK" >&2
    echo "Re-run with --force to replace it." >&2
    exit 1
  fi
  echo "Replacing foreign pre-commit hook (--force given)." >&2
fi

cat > "$HOOK" <<'HOOK_BODY'
#!/bin/sh
# >>> donald self-knowledge hook >>>
# Auto-refreshes context/self/donald.md from the codebase on every
# commit and stages it. Local-only and non-gating: any failure is
# swallowed so it can never block a commit.
REPO_ROOT=$(git rev-parse --show-toplevel)
DOC="$REPO_ROOT/context/self/donald.md"
if PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
     python3 -m donald.cli self-knowledge --refresh >/dev/null 2>&1; then
  git add "$DOC" 2>/dev/null || true
else
  echo "donald: self-knowledge refresh skipped (could not run)" >&2
fi
exit 0
# <<< donald self-knowledge hook <<<
HOOK_BODY

chmod +x "$HOOK"
echo "Installed donald self-knowledge pre-commit hook at $HOOK"
