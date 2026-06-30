import unittest

from security.log_redact import redact


class TestRedact(unittest.TestCase):
    def test_masks_each_shape(self):
        fixture = (
            "key=sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUV "
            "stripe=sk_live_ABCDEFGHIJ1234567890 "
            "gh=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "
            "Authorization: Bearer abcdef.ghijkl.mnopqr "
            "jwt=eyJhbGciOi.eyJzdWIiOi.SflKxwRJSM "
            "email=alice.smith@example.com "
            "card=4242 4242 4242 4242 "
            "dsn=postgres://user:supersecret@db.host:5432/app"
        )
        out = redact(fixture, max_len=0)
        # Secrets gone
        self.assertNotIn("ABCDEFGHIJKLMNOPQRSTUV", out)
        self.assertNotIn("supersecret", out)
        self.assertNotIn("api03-ABCDEFGHIJ", out)
        self.assertNotIn("alice.smith", out)
        self.assertNotIn("4242 4242 4242 4242", out)
        # Shapes masked
        self.assertIn("Authorization: <redacted>", out)
        self.assertIn("<jwt:redacted>", out)
        self.assertIn("@example.com", out)         # domain kept
        self.assertIn("a***@example.com", out)     # local masked
        self.assertIn("4242", out)                 # last4 kept
        self.assertIn("postgres://user:<pass>@db.host", out)

    def test_truncation_separate_from_regex(self):
        out = redact("x" * 1000, max_len=100)
        self.assertTrue(out.startswith("x" * 100))
        self.assertIn("(+900 chars)", out)

    def test_secret_cannot_survive_past_truncation(self):
        # Secret sits beyond max_len; it must be masked before truncation.
        text = ("ok " * 50) + "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        out = redact(text, max_len=10_000)
        self.assertNotIn("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", out)

    def test_clean_text_unchanged(self):
        clean = "Tool fetch_weather returned: sunny, 21C in Berlin."
        self.assertEqual(redact(clean), clean)

    def test_non_string_input(self):
        self.assertEqual(redact({"a": 1}), "{'a': 1}")


if __name__ == "__main__":
    unittest.main()
