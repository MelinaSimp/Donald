import unittest

from security.subprocess_env import shell_minimal, with_keys, full


class TestSubprocessEnv(unittest.TestCase):
    def setUp(self):
        self.env = {
            "HOME": "/home/u",
            "PATH": "/usr/bin",
            "USER": "u",
            "LANG": "en_US.UTF-8",
            "STRIPE_API_KEY": "sk_live_xxx",
            "GITHUB_TOKEN": "ghp_xxx",
            "DATABASE_URL": "postgres://u:p@h/db",
            "ANTHROPIC_API_KEY": "sk-ant-xxx",
        }

    def test_shell_minimal_strips_secrets(self):
        env = shell_minimal(self.env)
        self.assertIn("HOME", env)
        self.assertIn("PATH", env)
        for secret in ("STRIPE_API_KEY", "GITHUB_TOKEN", "DATABASE_URL", "ANTHROPIC_API_KEY"):
            self.assertNotIn(secret, env)

    def test_with_keys_adds_only_named(self):
        env = with_keys("ANTHROPIC_API_KEY", environ=self.env)
        self.assertEqual(env["ANTHROPIC_API_KEY"], "sk-ant-xxx")
        self.assertNotIn("STRIPE_API_KEY", env)
        self.assertNotIn("GITHUB_TOKEN", env)

    def test_with_keys_skips_absent(self):
        env = with_keys("NOT_SET", environ=self.env)
        self.assertNotIn("NOT_SET", env)

    def test_full_requires_reason(self):
        with self.assertRaises(ValueError):
            full("", environ=self.env)
        with self.assertRaises(ValueError):
            full("   ", environ=self.env)
        env = full("legacy build needs full toolchain env", environ=self.env)
        self.assertIn("STRIPE_API_KEY", env)


if __name__ == "__main__":
    unittest.main()
