import unittest

from security.killswitch import is_active, kill_switch_response, DEFAULT_ENV_VAR


class TestKillSwitch(unittest.TestCase):
    def test_truthy_values(self):
        for v in ("true", "1", "yes", "on", "TRUE", "On"):
            self.assertTrue(is_active(environ={DEFAULT_ENV_VAR: v}), v)

    def test_falsy_values(self):
        for v in ("false", "0", "no", "off", "", "nope"):
            self.assertFalse(is_active(environ={DEFAULT_ENV_VAR: v}), v)

    def test_unset_is_inactive(self):
        self.assertFalse(is_active(environ={}))

    def test_custom_env_var(self):
        self.assertTrue(is_active(env_var="MYAGENT_KILL", environ={"MYAGENT_KILL": "yes"}))

    def test_response_shape(self):
        r = kill_switch_response(agent_name="Trillion", env_var="MYAGENT_KILL")
        self.assertEqual(r["status"], "kill_switch_active")
        self.assertIn("Trillion", r["message"])
        self.assertIn("MYAGENT_KILL=false", r["message"])


if __name__ == "__main__":
    unittest.main()
