"""Probe configuration cannot skip gates or mutate normal PR source."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_hardening_checks import load

control = load("ci-negative-control")


class NegativeControls(unittest.TestCase):
    def test_normal_pr_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for stage in control.PROBES[1:]:
                self.assertFalse(control.inject(root, "none", stage))
            self.assertEqual(list(root.iterdir()), [])

    def test_only_selected_stage_is_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backend/src/core").mkdir(parents=True)
            (root / "backend/src/evals").mkdir()
            (root / "frontend/e2e").mkdir(parents=True)
            evaluation = root / "backend/src/evals/runner.py"
            evaluation.write_text("thresholds = thresholds or EvaluationThresholds()")
            self.assertFalse(control.inject(root, "eval", "mypy"))
            self.assertTrue(control.inject(root, "eval", "eval"))
            self.assertIn("router_accuracy=1.1", evaluation.read_text())
            self.assertTrue(control.inject(root, "mypy", "mypy"))
            self.assertIn(
                "value: int",
                (root / "backend/src/core/_ci_negative_probe.py").read_text(),
            )
            self.assertTrue(control.inject(root, "playwright", "playwright"))
            self.assertIn(
                "INTENTIONAL_PH004_FAILURE",
                (root / "frontend/e2e/ci-hardening.spec.ts").read_text(),
            )
            with self.assertRaises(ValueError):
                control.inject(root, "eval", "eval")

    def test_cli_cannot_activate_probe_in_a_pull_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(control, "ROOT", root),
                patch("sys.argv", ["ci-negative-control.py", "mypy"]),
                patch.dict(
                    "os.environ",
                    {
                        "PH_CI_PROBE": "mypy",
                        "GITHUB_ACTIONS": "true",
                        "GITHUB_EVENT_NAME": "pull_request",
                    },
                ),
            ):
                with self.assertRaises(SystemExit):
                    control.main()
            self.assertEqual(list(root.iterdir()), [])

    def test_invalid_probe_is_rejected(self):
        with self.assertRaises(ValueError):
            control.inject(Path("unused"), "skip-all", "eval")
