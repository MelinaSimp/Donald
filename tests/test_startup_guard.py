import unittest

from security.startup_guard import assert_safe_startup, StartupSecurityError, is_local_bind


class TestStartupGuard(unittest.TestCase):
    def test_dev_mode_public_bind_refuses(self):
        with self.assertRaises(StartupSecurityError):
            assert_safe_startup(dev_mode=True, bind_host="0.0.0.0")
        with self.assertRaises(StartupSecurityError):
            assert_safe_startup(dev_mode=True, bind_host="192.168.1.10")

    def test_dev_mode_localhost_ok(self):
        assert_safe_startup(dev_mode=True, bind_host="127.0.0.1")
        assert_safe_startup(dev_mode=True, bind_host="localhost")
        assert_safe_startup(dev_mode=True, bind_host="::1")

    def test_prod_public_bind_ok(self):
        assert_safe_startup(dev_mode=False, bind_host="0.0.0.0")

    def test_is_local_bind(self):
        self.assertTrue(is_local_bind("127.0.0.1"))
        self.assertTrue(is_local_bind("LOCALHOST"))
        self.assertFalse(is_local_bind("0.0.0.0"))


if __name__ == "__main__":
    unittest.main()
