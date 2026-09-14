"""Negative fixtures ensure policy checks reject unsafe binds and version drift."""

import importlib.util
import unittest
from pathlib import Path


def load(name):
    path = Path(__file__).resolve().parents[1] / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compose = load("check-compose-loopback")
metadata = load("check-runtime-versions")
policy = load("check-repository-policy")


class HardeningChecks(unittest.TestCase):
    def test_loopback(self):
        self.assertEqual(
            compose.validate(
                {"services": {"app": {"ports": [{"host_ip": "127.0.0.1"}]}}}
            ),
            1,
        )

    def test_non_loopback_and_empty_fail(self):
        for ip in (None, "", "0.0.0.0", "::", "::1", "192.168.1.2"):
            with self.subTest(ip=ip), self.assertRaises(ValueError):
                compose.validate({"services": {"app": {"ports": [{"host_ip": ip}]}}})
        with self.assertRaises(ValueError):
            compose.validate({"services": {}})

    def test_runtime_consistency_and_mismatch(self):
        metadata.validate(
            "1.2.3",
            {"version": "1.2.3"},
            {"version": "1.2.3", "status": "ok"},
            {"info": {"version": "1.2.3"}},
        )
        with self.assertRaises(ValueError):
            metadata.validate(
                "1.2.4",
                {"version": "1.2.3"},
                {"version": "1.2.3", "status": "ok"},
                {"info": {"version": "1.2.3"}},
            )
        with self.assertRaises(ValueError):
            metadata.validate(
                "1.2.3",
                {"version": "1.2.3"},
                {"version": "1.2.3", "status": "degraded"},
                {"info": {"version": "1.2.3"}},
            )

    def test_length_floor(self):
        policy.validate_length("example.py", "x\n" * 500)
        with self.assertRaises(ValueError):
            policy.validate_length("example.py", "x\n" * 501)

    def test_pr_versions_not_last_commit(self):
        policy.validate_versions(("1.0.0", "2.0.0"), ("1.0.1", "2.0.0"), True)
        policy.validate_versions(("1.0.0", "2.0.0"), ("1.0.0", "2.0.0"), False)
        with self.assertRaises(ValueError):
            policy.validate_versions(("1.0.0", "2.0.0"), ("1.0.0", "2.0.0"), True)
        with self.assertRaises(ValueError):
            policy.validate_versions(("1.0.0", "2.0.0"), ("0.9.0", "2.0.1"), True)


if __name__ == "__main__":
    unittest.main()
