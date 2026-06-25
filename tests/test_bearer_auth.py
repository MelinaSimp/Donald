import unittest

from security.bearer_auth import BearerVerifier, extract_bearer


class TestBearerAuth(unittest.TestCase):
    def test_overlap_window_both_valid(self):
        v = BearerVerifier(current="new-token-123", previous="old-token-456")
        self.assertEqual(v.verify("new-token-123"), "current")
        self.assertEqual(v.verify("old-token-456"), "previous")
        self.assertIsNone(v.verify("garbage"))

    def test_after_prev_cleared_only_new(self):
        v = BearerVerifier(current="new-token-123")  # PREV unset
        self.assertTrue(v.is_valid("new-token-123"))
        self.assertFalse(v.is_valid("old-token-456"))

    def test_empty_presented_is_invalid(self):
        v = BearerVerifier(current="new-token-123", previous="old-token-456")
        self.assertIsNone(v.verify(None))
        self.assertIsNone(v.verify(""))

    def test_requires_current(self):
        with self.assertRaises(ValueError):
            BearerVerifier(current="")

    def test_extract_bearer(self):
        self.assertEqual(extract_bearer("Bearer abc123"), "abc123")
        self.assertEqual(extract_bearer("bearer abc123"), "abc123")
        self.assertIsNone(extract_bearer("Basic abc123"))
        self.assertIsNone(extract_bearer(None))
        self.assertIsNone(extract_bearer("Bearer "))

    def test_verify_header(self):
        v = BearerVerifier(current="tok")
        self.assertEqual(v.verify_header("Bearer tok"), "current")
        self.assertIsNone(v.verify_header("Bearer nope"))


if __name__ == "__main__":
    unittest.main()
