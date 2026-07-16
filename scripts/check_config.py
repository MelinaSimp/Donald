#!/usr/bin/env python3
"""Config readiness — which third-party keys are set, and what each unlocks.

Run before a deploy to see what's live and what's still stubbed:

    python scripts/check_config.py

Nothing here prints secret values — only whether each is present.
"""

from __future__ import annotations

import os
import sys

# (env var, what it unlocks, required-for-core?)
CHECKS = [
    ("BACKEND_SECRET_KEY", "Encrypt integration tokens at rest (M1)", True),
    ("DATABASE_URL", "Postgres in prod (else SQLite dev file)", False),
    ("ANTHROPIC_API_KEY", "The model brain (else offline mock)", True),
    ("EMBEDDINGS_PROVIDER", "Learned embeddings for memory (else lexical)", False),
    ("GOOGLE_CLIENT_ID", "Connect Google (M4)", False),
    ("GOOGLE_CLIENT_SECRET", "Connect Google (M4)", False),
    ("GITHUB_CLIENT_ID", "Connect GitHub (M4)", False),
    ("GITHUB_CLIENT_SECRET", "Connect GitHub (M4)", False),
    ("SLACK_CLIENT_ID", "Connect Slack (M4)", False),
    ("SLACK_CLIENT_SECRET", "Connect Slack (M4)", False),
    ("OAUTH_REDIRECT_BASE", "Public URL for OAuth callbacks (M4)", False),
    ("STRIPE_SECRET_KEY", "Billing / subscriptions (M5)", False),
    ("STRIPE_PRICE_ID", "The plan users subscribe to (M5)", False),
    ("STRIPE_WEBHOOK_SECRET", "Verify Stripe webhooks (M5)", False),
    ("DEEPGRAM_API_KEY", "High-quality speech-to-text (voice)", False),
    ("ELEVENLABS_API_KEY", "High-quality text-to-speech (voice)", False),
    ("UPDATE_MANIFEST_PATH", "Serve desktop auto-updates (M6)", False),
]

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def main() -> int:
    print("Donald — config readiness\n")
    missing_core = []
    for env, unlocks, core in CHECKS:
        set_ = bool(os.getenv(env))
        mark = f"{GREEN}●{RESET}" if set_ else f"{RED}○{RESET}"
        tag = f"{DIM}(core){RESET}" if core else ""
        print(f"  {mark} {env:<24} {DIM}{unlocks}{RESET} {tag}")
        if core and not set_:
            missing_core.append(env)

    print()
    if missing_core:
        print(f"{RED}Not launch-ready{RESET}: core keys missing → {', '.join(missing_core)}")
        return 1
    print(f"{GREEN}Core is ready.{RESET} Optional integrations light up as you add their keys.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
