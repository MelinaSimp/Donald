import unittest

from security.audit import SecurityState, compute_audit, score_color
from security.approval import hardline_pattern_count


def healthy_state(**overrides):
    base = dict(
        kill_switch_active=False,
        llm_api_key_set=True,
        bearer_token_set=True,
        approval_mode="smart",
        dev_mode=False,
        bind_host="127.0.0.1",
        gate_paths_total=4,
        gate_paths_covered=4,
        log_redaction_active=True,
        subprocess_envs_stripped=True,
        hardline_pattern_count=hardline_pattern_count(),
        csp_status="enforcing",
        csrf_origin_gate=True,
        token_scope_audited=True,
        db_readonly_active=True,
        cve_record={"cve_count": 0, "error_message": None, "generated_at": 1_000_000.0},
        now=lambda: 1_000_000.0,
    )
    base.update(overrides)
    return SecurityState(**base)


class TestAudit(unittest.TestCase):
    def test_healthy_is_green(self):
        result = compute_audit(healthy_state())
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["color"], "green")
        names = {s["name"] for s in result["signals"]}
        # all 14 signals present
        self.assertIn("kill-switch", names)
        self.assertIn("cve-scan", names)
        self.assertEqual(len(result["signals"]), 14)

    def test_kill_switch_dominates(self):
        result = compute_audit(healthy_state(kill_switch_active=True))
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["color"], "red")

    def test_approval_off_drops_score(self):
        healthy = compute_audit(healthy_state())["score"]
        off = compute_audit(healthy_state(approval_mode="off"))["score"]
        self.assertEqual(healthy - off, 25)

    def test_dangerous_public_bind(self):
        sig = next(
            s for s in compute_audit(healthy_state(dev_mode=True, bind_host="0.0.0.0"))["signals"]
            if s["name"] == "dev-mode-bind"
        )
        self.assertEqual(sig["severity"], "critical")
        self.assertEqual(sig["delta"], -40)

    def test_gate_coverage_partial(self):
        sig = next(
            s for s in compute_audit(healthy_state(gate_paths_total=4, gate_paths_covered=2))["signals"]
            if s["name"] == "gate-coverage"
        )
        self.assertEqual(sig["value"], "2/4 paths")
        self.assertEqual(sig["delta"], -10)

    def test_cve_findings_capped(self):
        rec = {"cve_count": 100, "error_message": None, "generated_at": 1_000_000.0}
        sig = next(
            s for s in compute_audit(healthy_state(cve_record=rec))["signals"]
            if s["name"] == "cve-scan"
        )
        self.assertEqual(sig["delta"], -25)  # capped

    def test_cve_stale(self):
        # 20 days before the fixed "now" of 1_000_000.0 -> stale (>14d).
        rec = {"cve_count": 0, "error_message": None, "generated_at": 1_000_000.0 - 20 * 86400}
        sig = next(
            s for s in compute_audit(healthy_state(cve_record=rec))["signals"]
            if s["name"] == "cve-scan"
        )
        self.assertIn("stale", sig["value"])

    def test_score_color_thresholds(self):
        self.assertEqual(score_color(85), "green")
        self.assertEqual(score_color(84), "amber")
        self.assertEqual(score_color(60), "amber")
        self.assertEqual(score_color(59), "red")


if __name__ == "__main__":
    unittest.main()
