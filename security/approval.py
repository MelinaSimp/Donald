"""3.1 - Tiered approval for code-execution tools.

Threat T3 (destructive command execution): the LLM is asked -- innocently or
via injection -- to run ``rm -rf /``, ``git push --force``, or ``DELETE FROM
users``. ``ApprovalGate`` evaluates a command against three layers:

  * HARDLINE blocklist -- immutable; blocks in EVERY mode (including ``off``)
    and cannot be bypassed by ``_confirmed=True``. Small and precise on
    purpose: a false positive here has no escape hatch.
  * HIGH-risk patterns  -- in ``smart`` mode return confirmation_required.
  * UNCERTAIN patterns   -- in ``smart`` mode return confirmation_required.

Modes:
  * ``off``    -- only hardline applies; everything else runs.
  * ``smart``  -- regex risk-rating; ``low`` auto-runs, ``uncertain``/``high``
                  need confirmation.
  * ``manual`` -- every call needs confirmation.

Re-invocation contract: on a ``confirmation_required`` decision the LLM calls
your ``await_confirmation`` tool, then re-invokes the original tool with
``_confirmed=True``. That flag bypasses smart/manual -- but NEVER hardline.

The mode is read live (pass a callable) so a toggle takes effect without a
restart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple, Union

# --- Risk levels (ordered) ---
RISK_NONE = "none"
RISK_LOW = "low"
RISK_UNCERTAIN = "uncertain"
RISK_HIGH = "high"
RISK_HARDLINE = "hardline"

_MODES = ("off", "smart", "manual")


# ---------------------------------------------------------------------------
# HARDLINE blocklist -- immutable. (name, matcher) where matcher is a compiled
# regex or a callable(str)->bool for cases too imprecise for a single regex.
# ---------------------------------------------------------------------------

_RM_CALL_RE = re.compile(r"(?i)(?:^|[;&|]|\bsudo\s+|\bxargs\s+|&&|\bthen\s+)\s*rm\b([^;&|\n]*)")
# Targets that make an `rm -rf` a HARDLINE (irrecoverable system wipe).
_ROOT_TARGETS = frozenset(
    {"/", "/*", "/.", "~", "/root", "/etc", "/usr", "/var", "/bin", "/sbin",
     "/lib", "/lib64", "/boot", "/sys", "/dev", "/home", "/opt", "/proc"}
)


def _rm_flags_and_targets(args: str) -> Tuple[bool, bool, List[str]]:
    """Return (has_recursive, has_force, targets) for one rm arg string."""
    has_r = has_f = False
    targets: List[str] = []
    for tok in args.split():
        if tok.startswith("--"):
            low = tok.lower()
            if "recursive" in low:
                has_r = True
            elif "force" in low:
                has_f = True
            elif low == "--no-preserve-root":
                # Explicit intent to wipe root.
                has_r = has_f = True
                targets.append("/")
        elif tok.startswith("-"):
            body = tok[1:].lower()
            if "r" in body:
                has_r = True
            if "f" in body:
                has_f = True
        else:
            targets.append(tok)
    return has_r, has_f, targets


def _is_rm_rf_root(cmd: str) -> bool:
    for m in _RM_CALL_RE.finditer(cmd):
        has_r, has_f, targets = _rm_flags_and_targets(m.group(1))
        if has_r and has_f:
            for t in targets:
                if t in _ROOT_TARGETS or re.fullmatch(r"/\*?\.?", t):
                    return True
    return False


def _is_rm_rf_bounded(cmd: str) -> bool:
    """rm -rf with a concrete (non-root) target -> HIGH, not hardline."""
    for m in _RM_CALL_RE.finditer(cmd):
        has_r, has_f, targets = _rm_flags_and_targets(m.group(1))
        if has_r and has_f and targets:
            return True
    return False


HARDLINE_RULES: List[Tuple[str, Union[re.Pattern, Callable[[str], bool]]]] = [
    ("rm-rf-root", _is_rm_rf_root),
    ("fork-bomb", re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")),
    ("dd-to-disk", re.compile(r"(?i)\bdd\b[^\n]*\bof=/dev/(sd|disk|nvme|hd|xvd|mmcblk)")),
    ("mkfs-device", re.compile(r"(?i)\bmkfs(\.\w+)?\s+[^\n]*/dev/")),
    ("redirect-to-disk", re.compile(r"(?i)>\s*/dev/(sd|disk|nvme|hd|xvd|mmcblk)")),
    ("shred-root", re.compile(r"(?i)\bshred\b[^\n]*\s/(?:\s|$|\*)")),
    ("chmod-777-root", re.compile(r"(?i)\bchmod\s+(?:-[a-z]*R[a-z]*\s+)?[0-7]*777\s+/(?:\s|$|\w)")),
    ("chown-recursive-root", re.compile(r"(?i)\bchown\s+(?:-[a-z]*R[a-z]*\s+)[^\n]*\s/(?:\s|$)")),
    ("curl-pipe-shell", re.compile(r"(?i)\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(bash|sh|zsh|ksh)\b")),
]


# ---------------------------------------------------------------------------
# Smart-mode HIGH-risk patterns.
# ---------------------------------------------------------------------------
HIGH_RULES: List[Tuple[str, Union[re.Pattern, Callable[[str], bool]]]] = [
    ("rm-rf-bounded", _is_rm_rf_bounded),
    ("drop-table", re.compile(r"(?i)\bdrop\s+(table|database|schema)\b")),
    # DELETE FROM <t> with no WHERE clause anywhere before end of statement.
    ("delete-without-where", re.compile(r"(?i)\bdelete\s+from\s+\S+(?![^;\n]*\bwhere\b)")),
    ("truncate-table", re.compile(r"(?i)\btruncate\s+(table\s+)?\w+")),
    ("git-push-force", re.compile(r"(?i)\bgit\s+push\b[^\n]*(--force\b|--force-with-lease\b|\s-f\b)")),
    ("git-reset-hard", re.compile(r"(?i)\bgit\s+reset\s+--hard\b")),
    ("format-volume", re.compile(r"(?i)\b(format|wipe)\s+(disk|drive|volume|partition)\b")),
    ("write-secret-file", re.compile(r"(?i)(>|>>|\btee\b)\s+\S*(\.env\b|/\.ssh/|credentials\b|id_rsa\b|\.pypirc\b|\.npmrc\b)")),
]


# ---------------------------------------------------------------------------
# Smart-mode UNCERTAIN patterns.
# ---------------------------------------------------------------------------
UNCERTAIN_RULES: List[Tuple[str, Union[re.Pattern, Callable[[str], bool]]]] = [
    ("mentions-production", re.compile(r"(?i)\b(production|prod)\b")),
    ("references-dotenv", re.compile(r"(?i)\.env\b")),
    ("uses-sudo", re.compile(r"(?i)\bsudo\b")),
    ("curl-pipeline", re.compile(r"(?i)\bcurl\b[^\n]*\|")),
    ("kill-9", re.compile(r"(?i)\bkill\s+-9\b")),
    ("npm-publish", re.compile(r"(?i)\bnpm\s+publish\b")),
    ("docker-rm-force", re.compile(r"(?i)\bdocker\s+rm\s+-f\b")),
]


def _matches(rule_matcher: Union[re.Pattern, Callable[[str], bool]], cmd: str) -> bool:
    if callable(rule_matcher) and not isinstance(rule_matcher, re.Pattern):
        return bool(rule_matcher(cmd))
    return bool(rule_matcher.search(cmd))


def _first_match(rules, cmd: str) -> Optional[str]:
    for name, matcher in rules:
        if _matches(matcher, cmd):
            return name
    return None


@dataclass
class ApprovalDecision:
    """Outcome of evaluating one command."""

    allowed: bool
    risk: str
    confirmation_required: bool = False
    matched_rule: Optional[str] = None
    reason: str = ""

    def to_response(self) -> dict:
        """Render the structured tool response the LLM consumes."""
        if self.confirmation_required:
            return {
                "status": "confirmation_required",
                "risk": self.risk,
                "matched_rule": self.matched_rule,
                "message": self.reason,
            }
        if not self.allowed:
            return {
                "status": "blocked",
                "risk": self.risk,
                "matched_rule": self.matched_rule,
                "message": self.reason,
            }
        return {"status": "ok", "risk": self.risk}


def hardline_match(command: str) -> Optional[str]:
    """Return the name of the first hardline rule that matches, else None."""
    return _first_match(HARDLINE_RULES, command or "")


def hardline_pattern_count() -> int:
    return len(HARDLINE_RULES)


ModeSource = Union[str, Callable[[], str]]


class ApprovalGate:
    """Evaluate commands against the hardline blocklist + tiered approval.

    ``mode`` may be a string or a zero-arg callable returning the current mode
    string, so a live toggle (env var, settings row) takes effect without a
    restart.
    """

    def __init__(self, mode: ModeSource = "smart") -> None:
        self._mode_source = mode

    @property
    def mode(self) -> str:
        m = self._mode_source() if callable(self._mode_source) else self._mode_source
        if m not in _MODES:
            raise ValueError(f"approval mode must be one of {_MODES}, got {m!r}")
        return m

    def evaluate(self, command: str, confirmed: bool = False) -> ApprovalDecision:
        command = command or ""

        # 1) Hardline -- always, in every mode, regardless of _confirmed.
        hl = hardline_match(command)
        if hl:
            return ApprovalDecision(
                allowed=False,
                risk=RISK_HARDLINE,
                confirmation_required=False,
                matched_rule=hl,
                reason=(
                    f"Hardline-blocked ({hl}). This cannot be overridden in any mode "
                    "or by confirmation. Rephrase the command rather than relaxing the rule."
                ),
            )

        mode = self.mode

        # 2) off -- only hardline applies; everything else runs.
        if mode == "off":
            return ApprovalDecision(allowed=True, risk=RISK_LOW)

        # Rate the command once.
        high = _first_match(HIGH_RULES, command)
        uncertain = None if high else _first_match(UNCERTAIN_RULES, command)
        risk = RISK_HIGH if high else (RISK_UNCERTAIN if uncertain else RISK_LOW)
        matched = high or uncertain

        # 3) manual -- everything needs confirmation.
        if mode == "manual":
            if confirmed:
                return ApprovalDecision(allowed=True, risk=risk, matched_rule=matched)
            return ApprovalDecision(
                allowed=False,
                risk=risk if risk != RISK_LOW else RISK_LOW,
                confirmation_required=True,
                matched_rule=matched,
                reason="Manual approval mode: confirm before this command runs.",
            )

        # 4) smart -- low auto-runs; uncertain/high need confirmation.
        if risk == RISK_LOW:
            return ApprovalDecision(allowed=True, risk=RISK_LOW)
        if confirmed:
            return ApprovalDecision(allowed=True, risk=risk, matched_rule=matched)
        return ApprovalDecision(
            allowed=False,
            risk=risk,
            confirmation_required=True,
            matched_rule=matched,
            reason=f"{risk}-risk command ({matched}); confirm before it runs.",
        )
