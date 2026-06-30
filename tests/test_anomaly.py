import unittest

from security.anomaly import AnomalyGate


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class TestAnomalyGate(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.gate = AnomalyGate(clock=self.clock)

    def test_send_email_cap(self):
        for i in range(5):
            res = self.gate.check_and_record("send_email")
            self.assertEqual(res["status"], "ok", f"call {i}")
        res = self.gate.check_and_record("send_email")
        self.assertEqual(res["status"], "anomaly_gate_blocked")
        self.assertEqual(res["count"], 5)
        self.assertEqual(res["limit"], 5)

    def test_blocked_call_not_recorded(self):
        for _ in range(5):
            self.gate.check_and_record("send_email")
        self.gate.check_and_record("send_email")  # blocked
        # advance just past window; window is 3600
        self.clock.advance(3601)
        res = self.gate.check_and_record("send_email")
        self.assertEqual(res["status"], "ok")

    def test_prefix_cap_matches_delete_star(self):
        for _ in range(3):
            res = self.gate.check_and_record("delete_account")
            self.assertEqual(res["status"], "ok")
        res = self.gate.check_and_record("delete_account")
        self.assertEqual(res["status"], "anomaly_gate_blocked")
        self.assertEqual(res["cap_key"], "delete_")

    def test_uncapped_tool_runs_freely(self):
        for _ in range(100):
            res = self.gate.check_and_record("fetch_weather")
            self.assertEqual(res["status"], "ok")
            self.assertTrue(res.get("uncapped"))


if __name__ == "__main__":
    unittest.main()
