"""1.3 - Subprocess env stripping.

Threat T1 / T5 (key compromise & tool abuse): every ``subprocess.run`` /
``create_subprocess_exec`` / ``child_process.spawn`` that omits ``env``
inherits the *full* parent environment -- including STRIPE_*, GITHUB_*, DB
passwords, and your LLM key -- into a process that may be running git,
ffmpeg, or attacker-influenced shell. One stack trace or argv leak from that
child exposes everything.

Pass an explicit, minimal ``env`` at every spawn site:

    import subprocess
    from security.subprocess_env import shell_minimal, with_keys, full

    subprocess.run(["git", "status"], env=shell_minimal())            # generic
    subprocess.run(["claude", "-p", prompt],
                   env=with_keys("ANTHROPIC_API_KEY"))                 # needs LLM key
    subprocess.run(cmd, env=full("legacy build needs full PATH+toolchain vars"))

``full()`` requires a non-empty ``reason`` so every full-inheritance callsite
carries its justification into the diff for review.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, Optional

# OS baseline keys a normal CLI tool needs to function. No secrets here.
_POSIX_BASELINE = [
    "HOME",
    "PATH",
    "USER",
    "LOGNAME",
    "LANG",
    "LANGUAGE",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TMP",
    "TEMP",
    "SHELL",
    "PWD",
    "TZ",
    "TERM",
    # GUI / X helpers some tools (osascript, headless chromium) want.
    "DISPLAY",
    "XAUTHORITY",
    "XDG_RUNTIME_DIR",
]

_WINDOWS_BASELINE = [
    "SYSTEMROOT",
    "WINDIR",
    "PATH",
    "PATHEXT",
    "COMSPEC",
    "TEMP",
    "TMP",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
]


def _baseline_keys() -> list:
    return _WINDOWS_BASELINE if sys.platform.startswith("win") else _POSIX_BASELINE


def shell_minimal(environ: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return only the OS baseline keys present in the environment.

    Use for git, ffmpeg, osascript, and generic system tools that have no
    business seeing your credentials.
    """
    src = os.environ if environ is None else environ
    return {k: src[k] for k in _baseline_keys() if k in src}


def with_keys(*keys: str, environ: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """``shell_minimal()`` plus the explicitly named keys (when present).

    Use for code-execution tools that legitimately need a specific
    credential, e.g. spawning the LLM CLI: ``with_keys("ANTHROPIC_API_KEY")``.
    Keys absent from the environment are simply omitted (no KeyError) so a
    misconfigured deploy fails loudly in the child, not here.
    """
    src = os.environ if environ is None else environ
    env = shell_minimal(src)
    for k in keys:
        if k in src:
            env[k] = src[k]
    return env


def full(reason: str, environ: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Full inherited environment -- requires a non-empty justification.

    The ``reason`` argument exists solely so the diff reviewer sees *why*
    full inheritance was chosen at this callsite. Most spawn sites do not
    need this; prefer ``shell_minimal()`` or ``with_keys()``.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(
            "full() requires a non-empty reason explaining why this subprocess "
            "needs the entire inherited environment (all secrets included)."
        )
    src = os.environ if environ is None else environ
    return dict(src)
