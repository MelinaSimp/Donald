import unittest

from security.auth_ratelimit import AuthRateLimiter, client_ip


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class TestAuthRateLimiter(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.lim = AuthRateLimiter(max_fails=10, window_seconds=300, lockout_seconds=900,
                                   clock=self.clock)

    def test_lockout_after_n_fails(self):
        ip = "1.2.3.4"
        for _ in range(10):
            allowed, _ = self.lim.check(ip)
            self.assertTrue(allowed)
            self.lim.record_fail(ip)
        # 11th request (N+1) is locked out
        allowed, retry = self.lim.check(ip)
        self.assertFalse(allowed)
        self.assertGreater(retry, 0)
        self.assertLessEqual(retry, 900)

    def test_resumes_after_window(self):
        ip = "1.2.3.4"
        for _ in range(10):
            self.lim.record_fail(ip)
        self.assertFalse(self.lim.check(ip)[0])
        self.clock.advance(901)
        self.assertTrue(self.lim.check(ip)[0])

    def test_success_does_not_count(self):
        ip = "5.6.7.8"
        for _ in range(20):
            allowed, _ = self.lim.check(ip)
            self.assertTrue(allowed)  # never increments on success path
        # record_success clears state
        self.lim.record_success(ip)
        self.assertTrue(self.lim.check(ip)[0])

    def test_old_fails_expire_from_window(self):
        ip = "9.9.9.9"
        for _ in range(9):
            self.lim.record_fail(ip)
        self.clock.advance(301)  # those 9 fall out of the window
        self.lim.record_fail(ip)  # only 1 in-window now
        self.assertTrue(self.lim.check(ip)[0])

    def test_client_ip_prefers_proxy_header(self):
        ip = client_ip({"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}, "10.0.0.1")
        self.assertEqual(ip, "203.0.113.7")
        ip2 = client_ip({"CF-Connecting-IP": "198.51.100.2"}, "10.0.0.1")
        self.assertEqual(ip2, "198.51.100.2")
        ip3 = client_ip({}, "127.0.0.1")
        self.assertEqual(ip3, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
