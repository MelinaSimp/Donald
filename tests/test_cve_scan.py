import os
import tempfile
import unittest

from security import cve_scan


class TestCveScan(unittest.TestCase):
    def test_scanner_not_installed_records_error(self):
        # Force FileNotFoundError by pointing PATH at an empty dir.
        orig_path = os.environ.get("PATH")
        with tempfile.TemporaryDirectory() as empty:
            os.environ["PATH"] = empty
            try:
                rec = cve_scan.run_scan("python")
            finally:
                if orig_path is not None:
                    os.environ["PATH"] = orig_path
        self.assertIsNotNone(rec["error_message"])
        self.assertEqual(rec["cve_count"], 0)
        self.assertEqual(rec["ecosystem"], "python")

    def test_unsupported_ecosystem(self):
        rec = cve_scan.run_scan("rust")
        self.assertIn("unsupported", rec["error_message"])

    def test_persist_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "scan", "cve.json")
            record = {"ecosystem": "python", "cve_count": 2, "findings": [], "generated_at": 1.0}
            cve_scan.persist_record(record, path)
            loaded = cve_scan.load_record(path)
            self.assertEqual(loaded["cve_count"], 2)

    def test_load_missing_returns_none(self):
        self.assertIsNone(cve_scan.load_record("/nonexistent/path/cve.json"))


if __name__ == "__main__":
    unittest.main()
