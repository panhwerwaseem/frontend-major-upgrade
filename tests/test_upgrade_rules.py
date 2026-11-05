import io
import json
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "frontend-major-upgrade" / "scripts"))

import upgrade_rules  # noqa: E402


def run_main(argv):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = upgrade_rules.main(argv)
    return code, buffer.getvalue()


class RuleTableTests(unittest.TestCase):
    def test_every_rule_passes_its_own_examples(self):
        self.assertEqual(upgrade_rules.check_rules(upgrade_rules.RULES), [])

    def test_every_rule_is_governed_by_a_tracked_package(self):
        tracked = set(name for names in upgrade_rules.TRACKED.values() for name in names)
        for rule in upgrade_rules.RULES:
            self.assertIn(rule["package"], tracked, rule["id"])

    def test_every_framework_has_a_guide_and_a_codemod_entry(self):
        for framework in upgrade_rules.ANCHOR:
            self.assertTrue(upgrade_rules.GUIDES[framework]["default"].startswith("https://"))
            self.assertTrue(upgrade_rules.CODEMODS[framework]["default"])

    def test_stage_note_keys_name_a_known_framework(self):
        for key in upgrade_rules.STAGE_NOTES:
            framework, major = key.split(":")
            self.assertIn(framework, upgrade_rules.ANCHOR)
            self.assertTrue(major == "*" or major.isdigit(), key)

    def test_check_reports_a_rule_that_fails_its_examples(self):
        broken = dict(upgrade_rules.RULES[0], id="broken", match=["root.render(<App />)"])
        problems = upgrade_rules.check_rules([broken])
        self.assertEqual(len(problems), 1)
        self.assertIn("should match but does not", problems[0])

    def test_check_reports_missing_fields_and_bad_patterns(self):
        self.assertIn("missing", upgrade_rules.check_rules([{"id": "x"}])[0])
        bad = dict(upgrade_rules.RULES[0], id="bad", pattern="(")
        self.assertIn("does not compile", upgrade_rules.check_rules([bad])[0])

    def test_modern_api_names_are_not_matched(self):
        by_id = dict((rule["id"], re.compile(rule["pattern"], re.M)) for rule in upgrade_rules.RULES)
        self.assertIsNone(by_id["react-legacy-context"].search("static contextType = ThemeContext;"))
        self.assertIsNone(by_id["react-dom-hydrate"].search("hydrateRoot(container, <App />);"))
        self.assertIsNone(by_id["react-string-ref"].search("<input ref={inputRef} />"))
        self.assertIsNone(by_id["next-sync-request-api"].search("const jar = await cookies();"))
        self.assertIsNone(by_id["react-function-default-props"].search("  static defaultProps = {};"))


class RuleCliTests(unittest.TestCase):
    def test_check_passes_on_the_shipped_table(self):
        code, output = run_main(["--check"])
        self.assertEqual(code, 0)
        self.assertIn("0 problem(s)", output)

    def test_framework_filter_keeps_only_that_frameworks_rules(self):
        code, output = run_main(["--framework", "angular", "--json"])
        self.assertEqual(code, 0)
        packages = set(rule["package"] for rule in json.loads(output)["rules"])
        self.assertEqual(packages, {"@angular/core", "@angular/material"})

    def test_next_projects_also_get_the_react_rules(self):
        _, output = run_main(["--framework", "next", "--json"])
        ids = [rule["id"] for rule in json.loads(output)["rules"]]
        self.assertIn("react-dom-render", ids)
        self.assertIn("next-font-package", ids)
        self.assertNotIn("angular-entry-components", ids)

    def test_listing_names_every_rule(self):
        code, output = run_main([])
        self.assertEqual(code, 0)
        for rule in upgrade_rules.RULES:
            self.assertIn(rule["id"], output)

    def test_unknown_framework_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught, redirect_stdout(io.StringIO()):
            stderr, sys.stderr = sys.stderr, io.StringIO()
            try:
                upgrade_rules.main(["--framework", "vue"])
            finally:
                sys.stderr = stderr
        self.assertEqual(caught.exception.code, 2)


class ValidateRepoTests(unittest.TestCase):
    def test_repository_passes_its_own_validator(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import validate
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = validate.main(["validate.py", str(ROOT)])
        self.assertEqual(code, 0, buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
