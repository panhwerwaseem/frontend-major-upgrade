import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "frontend-major-upgrade" / "scripts"))

import stage_ledger  # noqa: E402

PASS = [sys.executable, "-c", "print('12 passed')"]
FAIL = [sys.executable, "-c", "import sys; print('FAIL checkout.test.js'); sys.exit(3)"]


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.ledger = self.dir / "scratch" / "ledger.json"
        self.set_version("^17.0.2")

    def set_version(self, declared, installed=None):
        (self.dir / "package.json").write_text(json.dumps({"dependencies": {"react": declared}}))
        if installed:
            folder = self.dir / "node_modules" / "react"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "package.json").write_text(json.dumps({"version": installed}))

    def run_ledger(self, *argv):
        """Return (exit code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        action, rest = argv[0], list(argv[1:])
        with redirect_stdout(out), redirect_stderr(err):
            code = stage_ledger.main([action, "--ledger", str(self.ledger)] + rest)
        return code, out.getvalue(), err.getvalue()

    def verify(self, check, command, *extra):
        return self.run_ledger("verify", "--check", check, "--project", str(self.dir), *(list(extra) + ["--"] + command))

    def state(self):
        return json.loads(self.ledger.read_text())

    def start(self, start="17", target="19"):
        return self.run_ledger("start", "--package", "react", "--from", start, "--to", target)


class StartTests(LedgerTestCase):
    def test_start_creates_a_baseline_and_one_stage_per_major(self):
        code, out, _ = self.start()
        self.assertEqual(code, 0)
        state = self.state()
        self.assertEqual([s["name"] for s in state["stages"]], ["baseline", "17 -> 18", "18 -> 19"])
        self.assertEqual([s["major"] for s in state["stages"]], [17, 18, 19])
        self.assertEqual([s["status"] for s in state["stages"]], ["open", "pending", "pending"])
        self.assertEqual((state["current"], state["complete"]), (0, False))

    def test_start_refuses_to_overwrite_without_force(self):
        self.start()
        code, _, err = self.start()
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)
        self.assertEqual(self.run_ledger("start", "--package", "react", "--from", "17", "--to", "18", "--force")[0], 0)
        self.assertEqual(len(self.state()["stages"]), 2)

    def test_start_rejects_a_path_that_does_not_go_up(self):
        code, _, err = self.start("19", "19")
        self.assertEqual(code, 2)
        self.assertIn("--to must be above --from", err)


class VerifyTests(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.start()

    def test_passing_check_is_recorded_with_command_log_and_version_evidence(self):
        code, out, _ = self.verify("test", PASS)
        self.assertEqual(code, 0)
        self.assertIn("baseline: test PASS (exit 0, attempt 1", out)
        check = self.state()["stages"][0]["checks"]["test"]
        self.assertEqual((check["status"], check["exit_code"], check["command"]), ("pass", 0, PASS))
        self.assertIn('package.json dependencies.react "^17.0.2"', check["version_evidence"])
        self.assertEqual((self.ledger.parent / check["log"]).read_text().strip(), "12 passed")

    def test_failing_check_returns_1_and_shows_the_output_tail(self):
        code, out, _ = self.verify("test", FAIL)
        self.assertEqual(code, 1)
        self.assertIn("baseline: test FAIL (exit 3", out)
        self.assertIn("FAIL checkout.test.js", out)
        self.assertEqual(self.state()["stages"][0]["checks"]["test"]["status"], "fail")

    def test_rerun_replaces_the_result_and_counts_attempts(self):
        self.verify("test", FAIL)
        self.verify("test", PASS)
        check = self.state()["stages"][0]["checks"]["test"]
        self.assertEqual((check["status"], check["attempts"]), ("pass", 2))

    def test_timeout_counts_as_a_failure(self):
        code, out, _ = self.verify("test", [sys.executable, "-c", "import time; time.sleep(5)"], "--timeout", "0.5")
        self.assertEqual(code, 1)
        self.assertIn("TIMEOUT", out)
        self.assertEqual(self.state()["stages"][0]["checks"]["test"]["status"], "timeout")

    def test_baseline_is_refused_when_the_project_is_not_on_the_starting_major(self):
        self.set_version("^18.3.1")
        code, out, _ = self.verify("test", PASS)
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        self.assertIn("expects react 17", out)
        self.assertEqual(self.state()["stages"][0]["checks"], {})

    def test_stage_is_refused_until_the_installed_version_is_the_stage_major(self):
        self.verify("test", PASS)
        self.run_ledger("advance")
        code, out, _ = self.verify("test", PASS)             # still on 17
        self.assertEqual(code, 1)
        self.assertIn("stage '17 -> 18' expects react 18", out)
        self.set_version("^18.3.1", installed="17.0.2")       # range edited, install not run
        code, out, _ = self.verify("test", PASS)
        self.assertEqual(code, 1)
        self.assertIn('node_modules/react/package.json version "17.0.2"', out)
        self.set_version("^18.3.1", installed="18.3.1")
        self.assertEqual(self.verify("test", PASS)[0], 0)

    def test_jumping_two_majors_is_refused(self):
        self.verify("test", PASS)
        self.run_ledger("advance")
        self.set_version("^19.0.0")
        code, out, _ = self.verify("test", PASS)
        self.assertEqual(code, 1)
        self.assertIn("expects react 18", out)

    def test_skip_version_check_is_recorded(self):
        self.set_version("latest")
        self.assertEqual(self.verify("test", PASS)[0], 1)
        code, _, _ = self.verify("test", PASS, "--skip-version-check")
        self.assertEqual(code, 0)
        self.assertIn("--skip-version-check", self.state()["stages"][0]["checks"]["test"]["version_evidence"])

    def test_changed_command_is_flagged_against_the_baseline(self):
        self.verify("test", PASS)
        self.run_ledger("advance")
        self.set_version("^18.3.1")
        code, out, _ = self.verify("test", [sys.executable, "-c", "pass"])
        self.assertEqual(code, 0)
        self.assertIn("differs from the baseline 'test' command", out)
        self.assertTrue(self.state()["stages"][1]["checks"]["test"]["differs_from_baseline"])

    def test_usage_errors_exit_2(self):
        self.assertEqual(self.verify("Test Name", PASS)[0], 2)
        self.assertEqual(self.run_ledger("verify", "--check", "test", "--project", str(self.dir))[0], 2)
        code, _, err = self.verify("test", ["no-such-binary-xyz"])
        self.assertEqual(code, 2)
        self.assertIn("cannot run no-such-binary-xyz", err)
        code, _, err = self.run_ledger("verify", "--check", "test", "--project", str(self.dir / "nope"), "--", "true")
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)


class AdvanceTests(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.start()

    def test_advance_is_refused_with_no_checks(self):
        code, out, _ = self.run_ledger("advance")
        self.assertEqual(code, 1)
        self.assertIn("no check has been recorded", out)
        self.assertEqual(self.state()["current"], 0)

    def test_advance_is_refused_while_a_check_is_failing(self):
        self.verify("build", PASS)
        self.verify("test", FAIL)
        code, out, _ = self.run_ledger("advance")
        self.assertEqual(code, 1)
        self.assertIn("REFUSED to advance past 'baseline'", out)
        self.assertIn("check 'test' last result is fail", out)
        self.assertEqual(self.state()["current"], 0)

    def test_advance_is_refused_when_a_baseline_check_was_dropped(self):
        self.verify("build", PASS)
        self.verify("test", PASS)
        self.assertEqual(self.run_ledger("advance")[0], 0)
        self.set_version("^18.3.1")
        self.verify("build", PASS)
        code, out, _ = self.run_ledger("advance")
        self.assertEqual(code, 1)
        self.assertIn("check 'test' passed at baseline but has not been run for this stage", out)

    def test_full_path_completes_and_then_refuses_further_work(self):
        self.verify("test", PASS)
        self.assertEqual(self.run_ledger("advance")[0], 0)
        self.set_version("^18.3.1")
        self.verify("test", PASS)
        code, out, _ = self.run_ledger("advance")
        self.assertIn("Now open: '18 -> 19' (react 19)", out)
        self.set_version("^19.0.0")
        self.verify("test", PASS)
        code, out, _ = self.run_ledger("advance")
        self.assertEqual(code, 0)
        self.assertIn("Every stage is verified: react is on 19", out)
        state = self.state()
        self.assertTrue(state["complete"])
        self.assertEqual([s["status"] for s in state["stages"]], ["passed", "passed", "passed"])
        code, _, err = self.run_ledger("advance")
        self.assertEqual(code, 2)
        self.assertIn("complete", err)


class StatusAndNoteTests(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.start()

    def test_status_lists_stages_and_returns_1_while_a_check_fails(self):
        self.verify("build", PASS)
        self.verify("test", FAIL)
        code, out, _ = self.run_ledger("status")
        self.assertEqual(code, 1)
        self.assertIn("current stage: baseline", out)
        self.assertIn("build pass, test FAIL", out)
        self.assertIn("18 -> 19   pending", out)
        self.verify("test", PASS)
        self.assertEqual(self.run_ledger("status")[0], 0)

    def test_status_json_carries_the_ledger(self):
        code, out, _ = self.run_ledger("status", "--json")
        data = json.loads(out)
        self.assertEqual((code, data["exit_code"], data["ledger"]["package"]), (0, 0, "react"))

    def test_note_is_attached_to_the_current_stage(self):
        self.assertEqual(self.run_ledger("note", "ran the migration recipe")[0], 0)
        self.assertEqual(self.state()["stages"][0]["notes"], ["ran the migration recipe"])
        self.assertIn("note: ran the migration recipe", self.run_ledger("status")[1])

    def test_missing_or_foreign_ledger_is_an_input_error(self):
        self.ledger.unlink()
        code, _, err = self.run_ledger("status")
        self.assertEqual(code, 2)
        self.assertIn("no ledger", err)
        self.ledger.write_text('{"something": "else"}')
        code, _, err = self.run_ledger("advance")
        self.assertEqual(code, 2)
        self.assertIn("not a ledger written by this script", err)

    def test_no_subcommand_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught, redirect_stderr(io.StringIO()):
            stage_ledger.main([])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
