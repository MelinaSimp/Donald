"""3.4 - Dependency CVE scanning.

Threat T6 (supply-chain compromise): a malicious or vulnerable transitive
dependency. ``run_scan()`` wraps ``pip-audit`` (Python) / ``npm audit``
(Node) as a subprocess -- with a stripped env from ``subprocess_env`` -- and
returns a normalized record you can persist and surface.

A "scanner not installed" outcome is recorded as a record with
``error_message`` (not a crash) so the audit shield can flag it.

Expose two routes in your app:
    GET  /api/security/cve-status -> load_record(path)
    POST /api/security/cve-scan   -> persist_record(run_scan(...), path)

and schedule ``run_scan`` weekly via your task scheduler.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Dict, List, Optional

from .subprocess_env import shell_minimal

_TIMEOUT = 120


def _empty_record(ecosystem: str) -> Dict[str, object]:
    return {
        "ecosystem": ecosystem,
        "cve_count": 0,
        "findings": [],
        "scanner_version": None,
        "error_message": None,
        "generated_at": time.time(),
    }


def _run(cmd: List[str], cwd: Optional[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=shell_minimal(),  # T1/T6: no secrets into the scanner subprocess
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )


def _scan_python(project_dir: Optional[str]) -> Dict[str, object]:
    record = _empty_record("python")
    try:
        proc = _run(["pip-audit", "--format", "json"], project_dir)
    except FileNotFoundError:
        record["error_message"] = "pip-audit not installed (pip install pip-audit)"
        return record
    except subprocess.TimeoutExpired:
        record["error_message"] = f"pip-audit timed out after {_TIMEOUT}s"
        return record

    raw = (proc.stdout or "").strip()
    if not raw:
        # pip-audit exits non-zero with findings; empty stdout means a real error.
        record["error_message"] = (proc.stderr or "pip-audit produced no output").strip()[:500]
        return record
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        record["error_message"] = "could not parse pip-audit JSON output"
        return record

    # pip-audit JSON is either a list (older) or {"dependencies": [...]}.
    deps = data.get("dependencies", data) if isinstance(data, dict) else data
    findings: List[dict] = []
    for dep in deps or []:
        for vuln in dep.get("vulns", []) or []:
            findings.append(
                {
                    "package": dep.get("name"),
                    "version": dep.get("version"),
                    "id": vuln.get("id"),
                    "fix_versions": vuln.get("fix_versions", []),
                }
            )
    record["findings"] = findings
    record["cve_count"] = len(findings)
    return record


def _scan_node(project_dir: Optional[str]) -> Dict[str, object]:
    record = _empty_record("node")
    try:
        proc = _run(["npm", "audit", "--json"], project_dir)
    except FileNotFoundError:
        record["error_message"] = "npm not installed"
        return record
    except subprocess.TimeoutExpired:
        record["error_message"] = f"npm audit timed out after {_TIMEOUT}s"
        return record

    raw = (proc.stdout or "").strip()
    if not raw:
        record["error_message"] = (proc.stderr or "npm audit produced no output").strip()[:500]
        return record
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        record["error_message"] = "could not parse npm audit JSON output"
        return record

    findings: List[dict] = []
    for name, adv in (data.get("vulnerabilities") or {}).items():
        findings.append(
            {
                "package": name,
                "severity": adv.get("severity"),
                "via": [v if isinstance(v, str) else v.get("title") for v in adv.get("via", [])],
            }
        )
    record["findings"] = findings
    record["cve_count"] = len(findings)
    return record


def run_scan(ecosystem: str = "python", project_dir: Optional[str] = None) -> Dict[str, object]:
    """Run a CVE scan and return a normalized record (never raises on scanner errors)."""
    if ecosystem == "python":
        return _scan_python(project_dir)
    if ecosystem == "node":
        return _scan_node(project_dir)
    rec = _empty_record(ecosystem)
    rec["error_message"] = f"unsupported ecosystem {ecosystem!r}"
    return rec


def persist_record(record: Dict[str, object], path: str) -> None:
    """Persist a scan record to a sidecar JSON file."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)


def load_record(path: str) -> Optional[Dict[str, object]]:
    """Load the latest persisted scan record, or None if absent/unreadable."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
