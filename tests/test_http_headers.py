import unittest

from security.http_headers import security_headers, build_csp, csp_status, DEFAULT_CSP_DIRECTIVES


class TestHttpHeaders(unittest.TestCase):
    def test_static_headers_present(self):
        h = security_headers()
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")
        self.assertEqual(h["X-Frame-Options"], "DENY")
        self.assertEqual(h["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertIn("autoplay=(self)", h["Permissions-Policy"])

    def test_report_only_by_default(self):
        h = security_headers(report_only=True)
        self.assertIn("Content-Security-Policy-Report-Only", h)
        self.assertNotIn("Content-Security-Policy", h)

    def test_enforcing_when_flipped(self):
        h = security_headers(report_only=False)
        self.assertIn("Content-Security-Policy", h)
        self.assertNotIn("Content-Security-Policy-Report-Only", h)

    def test_reporting_endpoint_wired(self):
        h = security_headers()
        self.assertIn("Reporting-Endpoints", h)
        self.assertIn("/api/security/csp-report", h["Reporting-Endpoints"])

    def test_csp_refuses_unsafe_eval(self):
        bad = dict(DEFAULT_CSP_DIRECTIVES)
        bad["script-src"] = ["'self'", "'unsafe-eval'"]
        with self.assertRaises(ValueError):
            build_csp(bad)

    def test_csp_contents(self):
        csp = build_csp()
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("report-uri /api/security/csp-report", csp)

    def test_csp_status_helper(self):
        self.assertEqual(csp_status(report_only=True), "report-only")
        self.assertEqual(csp_status(report_only=False), "enforcing")
        self.assertEqual(csp_status(report_only=True, enabled=False), "disabled")


if __name__ == "__main__":
    unittest.main()
