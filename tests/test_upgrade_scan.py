import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "frontend-major-upgrade"
sys.path.insert(0, str(SKILL / "scripts"))

import upgrade_scan  # noqa: E402

FIXTURES = SKILL / "evals" / "files"


def scan_json(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = upgrade_scan.main(argv + ["--json"])
    return code, (json.loads(out.getvalue()) if out.getvalue() else None), err.getvalue()


def found(result, rule):
    """[(evidence, level, stage)] for one rule id."""
    return [(f["evidence"], f["level"], f["stage"]) for f in result["findings"] if f["rule"] == rule]


class ParseMajorTests(unittest.TestCase):
    def test_common_ranges(self):
        cases = {"^17.0.2": 17, "~16.8": 16, "17.x": 17, "18.3.1": 18, "v18.2.0": 18,
                 ">=16.8.0 <18": 16, "^17.0.0 || ^18.0.0": 17}
        for text, major in cases.items():
            self.assertEqual(upgrade_scan.parse_major(text), major, text)

    def test_ranges_without_a_version_give_none(self):
        for text in ("latest", "*", "workspace:*", "npm:preact@10", "github:facebook/react", "<18", None):
            self.assertIsNone(upgrade_scan.parse_major(text), text)


class RangeAdmitsTests(unittest.TestCase):
    def test_clear_answers(self):
        cases = [("^18.0.0", 18, True), ("^18.0.0", 19, False), ("^16.8 || ^17 || ^18", 19, False),
                 (">=16.8", 19, True), (">=16.8.0 <19", 19, False), (">=16.8.0 <19.0.0", 18, True),
                 ("<19.1.0", 19, True), ("*", 3, True), ("17.x", 18, False), ("16 - 18", 18, True),
                 ("16.0.0 - 18.2.0", 19, False), (">= 17", 19, True), ("^19.0.0-rc.1", 19, True),
                 ("<=18", 19, False), ("~0.14 || ^15", 0, True)]
        for text, major, expected in cases:
            self.assertIs(upgrade_scan.range_admits(text, major), expected, "%s / %d" % (text, major))

    def test_unknown_forms_are_not_guessed(self):
        self.assertIsNone(upgrade_scan.range_admits("next", 19))
        self.assertIsNone(upgrade_scan.range_admits("workspace:*", 19))


class StripCommentsTests(unittest.TestCase):
    def test_comments_are_blanked_and_line_numbers_kept(self):
        source = "a(); // ReactDOM.render(x)\n/* findDOMNode(\n this.refs */ b();\n"
        stripped = upgrade_scan.strip_comments(source)
        self.assertNotIn("ReactDOM", stripped)
        self.assertNotIn("findDOMNode", stripped)
        self.assertIn("b();", stripped)
        self.assertEqual(stripped.count("\n"), source.count("\n"))

    def test_slashes_inside_strings_are_kept(self):
        source = "const url = 'https://example.com/a'; const t = `// kept`; go();\n"
        self.assertEqual(upgrade_scan.strip_comments(source), source)

    def test_jsx_comment_is_blanked(self):
        self.assertNotIn("ref=", upgrade_scan.strip_comments('<p>{/* <input ref="q" /> */}</p>'))


class ReactLegacyFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code, cls.result, _ = scan_json([str(FIXTURES / "react-16-legacy"), "--to", "19"])

    def test_exit_code_and_path(self):
        self.assertEqual(self.code, 1)
        self.assertEqual((self.result["framework"], self.result["from"], self.result["to"]), ("react", 16, 19))
        self.assertEqual([s["name"] for s in self.result["stages"]],
                         ["react 16 -> 17", "react 17 -> 18", "react 18 -> 19"])

    def test_every_planted_removal_is_reported_at_the_react_19_stage(self):
        expected = {
            "react-dom-render": ["src/components/Modal.jsx:11", "src/index.js:6"],
            "react-dom-unmount": ["src/components/Modal.jsx:15"],
            "react-find-dom-node": ["src/components/SearchBox.jsx:9"],
            "react-string-ref": ["src/components/SearchBox.jsx:8", "src/components/SearchBox.jsx:15",
                                 "src/components/SearchBox.jsx:21"],
            "react-legacy-context": ["src/components/ThemeProvider.jsx:5", "src/components/ThemeProvider.jsx:7",
                                     "src/components/ThemeProvider.jsx:20"],
            "react-test-renderer-shallow": ["src/__tests__/SearchBox.test.js:3"],
        }
        for rule, places in expected.items():
            self.assertEqual(found(self.result, rule), [(place, "break", 2) for place in places], rule)

    def test_items_that_need_a_person_are_review_level(self):
        self.assertEqual(found(self.result, "react-dom-test-utils"),
                         [("src/__tests__/SearchBox.test.js:2", "review", 2)])
        self.assertEqual(found(self.result, "react-function-default-props"),
                         [("src/components/Badge.jsx:10", "review", 2)])

    def test_family_mismatch_is_reported_before_the_first_stage(self):
        self.assertEqual(found(self.result, "family-mismatch"),
                         [("package.json devDependencies.react-test-renderer", "break", None)])

    def test_comment_and_modern_apis_are_not_reported(self):
        evidence = [f["evidence"] for f in self.result["findings"]]
        self.assertNotIn("src/index.js:5", evidence)            # commented-out ReactDOM.render
        self.assertNotIn("src/components/Modal.jsx:6", evidence)  # static contextType
        self.assertNotIn("src/components/SearchBox.jsx:5", evidence)  # class static defaultProps
        self.assertEqual(self.result["summary"], {"deprecated": 0, "review": 2, "break": 12})

    def test_family_moves_together_and_guides_are_named(self):
        stage = self.result["stages"][2]
        self.assertEqual(stage["move_together"], ["react", "react-dom", "react-test-renderer"])
        self.assertIn("react-19-upgrade-guide", stage["guide"])
        self.assertTrue(any("codemod" in line for line in stage["codemods"]))

    def test_stopping_at_18_reports_render_as_deprecated_only(self):
        code, result, _ = scan_json([str(FIXTURES / "react-16-legacy"), "--to", "18"])
        levels = set(level for _, level, _ in found(result, "react-dom-render"))
        self.assertEqual(levels, {"deprecated"})
        self.assertEqual(found(result, "react-find-dom-node"), [])
        self.assertEqual(code, 1)  # the family mismatch still blocks

    def test_text_output_names_file_and_line(self):
        out = io.StringIO()
        with redirect_stdout(out):
            upgrade_scan.main([str(FIXTURES / "react-16-legacy"), "--to", "19"])
        text = out.getvalue()
        self.assertIn("path: 16 -> 17 -> 18 -> 19 (3 stages, one major each)", text)
        self.assertIn("src/index.js:6  ReactDOM.render(<App />, document.getElementById('root'));", text)
        self.assertIn("not proof of a safe upgrade", text)


class NextFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code, cls.result, _ = scan_json([str(FIXTURES / "next-13-app"), "--to", "16"])

    def test_detects_next_and_plans_three_stages(self):
        self.assertEqual(self.code, 1)
        self.assertEqual(self.result["framework"], "next")
        self.assertEqual(len(self.result["stages"]), 3)

    def test_react_moves_with_the_next_15_stage(self):
        self.assertEqual(self.result["stages"][0]["moves"], {"next": [13, 14]})
        self.assertEqual(self.result["stages"][1]["moves"], {"next": [14, 15], "react": [18, 19]})
        self.assertIn("react-dom", self.result["stages"][1]["move_together"])
        self.assertEqual(self.result["stages"][2]["moves"], {"next": [15, 16]})

    def test_planted_findings_land_on_the_right_stage(self):
        self.assertEqual(found(self.result, "next-export-script"), [("package.json scripts.export", "break", 0)])
        self.assertEqual(found(self.result, "next-font-package"), [("app/layout.js:1", "break", 0)])
        self.assertEqual(found(self.result, "next-og-image-response"), [("app/api/og/route.js:1", "break", 0)])
        self.assertEqual(found(self.result, "next-experimental-edge"), [("app/api/og/route.js:3", "break", 1)])
        self.assertEqual(found(self.result, "react-function-default-props"),
                         [("components/Card.jsx:10", "review", 1)])
        self.assertEqual(found(self.result, "next-lint-script"), [("package.json scripts.lint", "break", 2)])
        self.assertEqual(found(self.result, "next-sync-request-api"),
                         [("app/dashboard/page.js:5", "review", 2), ("app/dashboard/page.js:6", "review", 2)])

    def test_awaited_call_and_legacy_behavior_link_are_not_reported(self):
        files = [f["evidence"].split(":")[0] for f in self.result["findings"]]
        self.assertNotIn("app/account/page.js", files)
        self.assertNotIn("components/Nav.jsx", files)

    def test_eslint_config_mismatch_is_a_review_item(self):
        self.assertEqual(found(self.result, "family-mismatch"),
                         [("package.json devDependencies.eslint-config-next", "review", None)])

    def test_target_15_lists_sync_request_api_as_deprecated(self):
        _, result, _ = scan_json([str(FIXTURES / "next-13-app"), "--to", "15"])
        self.assertEqual([level for _, level, _ in found(result, "next-sync-request-api")],
                         ["deprecated", "deprecated"])
        self.assertEqual(found(result, "next-lint-script"), [])

    def test_from_override_plans_only_the_remaining_stage(self):
        code, result, _ = scan_json([str(FIXTURES / "next-13-app"), "--from", "15", "--to", "16"])
        self.assertEqual(code, 1)
        self.assertEqual([s["name"] for s in result["stages"]], ["next 15 -> 16"])
        # package.json still declares React 18, so the React 19 move lands on this stage.
        self.assertEqual(result["stages"][0]["moves"], {"next": [15, 16], "react": [18, 19]})
        self.assertEqual(sorted(set(f["rule"] for f in result["findings"])),
                         ["family-mismatch", "next-lint-script", "next-sync-request-api",
                          "react-function-default-props"])


class AngularFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code, cls.result, _ = scan_json([str(FIXTURES / "angular-15-material"), "--to", "17"])

    def test_one_major_per_stage_with_ng_update_commands(self):
        self.assertEqual(self.code, 1)
        self.assertEqual([s["name"] for s in self.result["stages"]],
                         ["@angular/core 15 -> 16", "@angular/core 16 -> 17"])
        self.assertIn("ng update @angular/core@16 @angular/cli@16", self.result["stages"][0]["codemods"][0])
        self.assertIn("ng update @angular/core@17 @angular/cli@17", self.result["stages"][1]["codemods"][0])

    def test_planted_findings(self):
        self.assertEqual(found(self.result, "angular-entry-components"),
                         [("src/app/app.module.ts:20", "break", 0)])
        self.assertEqual(found(self.result, "angular-material-legacy"), [
            ("src/app/app.component.ts:2", "break", 1), ("src/app/app.module.ts:4", "break", 1),
            ("src/app/app.module.ts:5", "break", 1), ("src/app/confirm-dialog.component.ts:2", "break", 1)])

    def test_both_family_mismatches_are_reported(self):
        self.assertEqual(found(self.result, "family-mismatch"), [
            ("package.json dependencies.@angular/cdk", "break", None),
            ("package.json dependencies.@angular/router", "break", None)])

    def test_material_and_cdk_move_with_the_framework(self):
        stage = self.result["stages"][0]
        self.assertEqual(stage["moves"]["@angular/material"], [15, 16])
        for name in ("@angular/cdk", "@angular/cli", "@angular/router", "@angular/material"):
            self.assertIn(name, stage["move_together"])


class CleanFixtureTests(unittest.TestCase):
    def test_modern_react_18_app_has_no_findings_on_the_way_to_19(self):
        code, result, _ = scan_json([str(FIXTURES / "react-18-modern"), "--to", "19"])
        self.assertEqual(code, 0)
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["stages"][0]["rules_in_table"], 11)
        self.assertGreaterEqual(result["files_scanned"], 6)

    def test_no_findings_even_at_the_strictest_level(self):
        code, _, _ = scan_json([str(FIXTURES / "react-18-modern"), "--to", "19", "--fail-on", "deprecated"])
        self.assertEqual(code, 0)

    def test_project_already_on_the_target_has_no_stages(self):
        code, result, _ = scan_json([str(FIXTURES / "react-18-modern"), "--to", "18"])
        self.assertEqual(code, 0)
        self.assertEqual(result["stages"], [])
        self.assertEqual(result["findings"], [])

    def test_fixtures_ship_no_installable_state(self):
        for pattern in ("node_modules", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"):
            self.assertEqual(list(FIXTURES.rglob(pattern)), [], pattern)


class TempProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write(self, relative, text):
        path = self.dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def package(self, **sections):
        self.write("package.json", json.dumps(sections))

    def test_installed_version_wins_over_the_declared_range(self):
        self.package(dependencies={"react": "^17.0.0"})
        self.write("node_modules/react/package.json", '{"version": "18.2.0"}')
        _, result, _ = scan_json([str(self.dir), "--to", "19"])
        self.assertEqual(result["from"], 18)
        self.assertIn("node_modules/react/package.json", result["version_evidence"])

    def test_dependency_with_excluding_peer_range_blocks_its_stage(self):
        self.package(dependencies={"react": "^17.0.0", "react-dom": "^17.0.0", "old-dnd": "^13.0.0",
                                   "wide": "1.0.0", "odd": "1.0.0"})
        self.write("node_modules/old-dnd/package.json",
                   '{"version": "13.1.1", "peerDependencies": {"react": "^16.8.5 || ^17.0.0 || ^18.0.0"}}')
        self.write("node_modules/wide/package.json", '{"version": "1.0.0", "peerDependencies": {"react": ">=16.8"}}')
        self.write("node_modules/odd/package.json", '{"version": "1.0.0", "peerDependencies": {"react": "next"}}')
        self.write("node_modules/react-dom/package.json",
                   '{"version": "17.0.2", "peerDependencies": {"react": "17.0.2"}}')
        code, result, _ = scan_json([str(self.dir), "--to", "19"])
        self.assertEqual(code, 1)
        self.assertEqual(found(result, "peer-range"),
                         [("node_modules/old-dnd/package.json peerDependencies.react", "break", 1)])
        self.assertEqual(result["peer_check"]["status"], "checked")
        self.assertEqual(result["peer_check"]["not_understood"], ['odd peerDependencies.react "next"'])

    def test_without_node_modules_the_peer_check_says_it_was_skipped(self):
        self.package(dependencies={"react": "^18.0.0"})
        _, result, _ = scan_json([str(self.dir), "--to", "19"])
        self.assertEqual(result["peer_check"]["status"], "skipped")

    def test_build_output_and_node_modules_are_not_scanned(self):
        self.package(dependencies={"react": "^18.0.0"})
        for folder in ("node_modules/lib", "dist", "build", ".next/server"):
            self.write(folder + "/bundle.js", "ReactDOM.render(a, b);\n")
        self.write("src/ok.js", "export const x = 1;\n")
        code, result, _ = scan_json([str(self.dir), "--to", "19"])
        self.assertEqual((code, result["findings"], result["files_scanned"]), (0, [], 1))

    def test_old_next_link_and_image_rules_apply_when_crossing_13(self):
        self.package(dependencies={"next": "12.3.4", "react": "^17.0.2", "react-dom": "^17.0.2"})
        self.write("pages/index.js", "import Link from 'next/link';\nimport Image from 'next/image';\n"
                                     "export default () => (\n  <Link href=\"/a\">\n    <a>A</a>\n  </Link>\n);\n")
        _, result, _ = scan_json([str(self.dir), "--to", "13"])
        self.assertEqual(found(result, "next-link-anchor-child"), [("pages/index.js:4", "break", 0)])
        self.assertEqual(found(result, "next-image-import"), [("pages/index.js:2", "review", 0)])
        self.assertEqual(result["stages"][0]["moves"], {"next": [12, 13], "react": [17, 18]})

    def test_fail_on_sets_the_blocking_level(self):
        self.package(dependencies={"react": "^18.0.0", "react-dom": "^18.0.0"})
        self.write("src/Badge.jsx", "export function Badge() { return null; }\nBadge.defaultProps = {};\n")
        code, result, _ = scan_json([str(self.dir), "--to", "19"])
        self.assertEqual((code, result["summary"]["review"]), (0, 1))
        code, _, _ = scan_json([str(self.dir), "--to", "19", "--fail-on", "review"])
        self.assertEqual(code, 1)

    def test_stage_outside_the_tables_says_so(self):
        self.package(dependencies={"next": "16.0.0", "react": "^19.0.0", "react-dom": "^19.0.0"})
        code, result, _ = scan_json([str(self.dir), "--to", "17"])
        stage = result["stages"][0]
        self.assertEqual((code, stage["rules_in_table"], stage["moves"]), (0, 0, {"next": [16, 17]}))
        self.assertTrue(any("does not say which react major" in note for note in stage["notes"]))

    def test_oversized_file_is_skipped_and_counted(self):
        self.package(dependencies={"react": "^18.0.0"})
        self.write("src/big.js", "ReactDOM.render(a, b);\n" + "x" * (upgrade_scan.MAX_FILE_BYTES + 1))
        code, result, _ = scan_json([str(self.dir), "--to", "19"])
        self.assertEqual((code, result["files_scanned"], result["files_skipped"]), (0, 0, 1))

    def test_angular_view_engine_opt_out_is_found_in_tsconfig(self):
        self.package(dependencies={"@angular/core": "^12.2.0"})
        self.write("tsconfig.app.json", '{\n  "angularCompilerOptions": {\n    "enableIvy": false\n  }\n}\n')
        _, result, _ = scan_json([str(self.dir), "--to", "13"])
        self.assertEqual(found(result, "angular-view-engine-opt-out"), [("tsconfig.app.json:3", "break", 0)])

    def test_input_errors_exit_2_with_a_message(self):
        cases = []
        cases.append((["--to", "19", str(self.dir / "missing")], "is not a directory"))
        code, _, err = scan_json([str(self.dir), "--to", "19"])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)
        self.write("package.json", "{not json")
        cases.append(([str(self.dir), "--to", "19"], "not valid JSON"))
        for argv, message in cases:
            code, result, err = scan_json(argv)
            self.assertEqual((code, result), (2, None))
            self.assertIn(message, err)

    def test_unusable_projects_are_explained(self):
        for sections, argv, message in [
            ({"dependencies": {"vue": "^3.0.0"}}, ["--to", "4"], "none of react, next or @angular/core"),
            ({"dependencies": {"react": "latest"}}, ["--to", "19"], "pass --from"),
            ({"dependencies": {"react": "^18.0.0"}}, ["--to", "17"], "downgrades are not planned"),
            ({"dependencies": {"react": "^18.0.0", "@angular/core": "^17.0.0"}}, ["--to", "19"], "pass --framework"),
            ({"dependencies": {"react": "^18.0.0"}}, ["--to", "19", "--framework", "angular"], "does not list"),
        ]:
            self.package(**sections)
            code, _, err = scan_json([str(self.dir)] + argv)
            self.assertEqual(code, 2, message)
            self.assertIn(message, err)

    def test_library_with_peer_dependency_is_noted(self):
        self.package(peerDependencies={"react": "^17.0.0 || ^18.0.0"})
        _, result, _ = scan_json([str(self.dir), "--to", "19"])
        self.assertEqual(result["from"], 17)
        self.assertTrue(any("library" in note for note in result["notes"]))

    def test_output_is_deterministic(self):
        argv = [str(FIXTURES / "next-13-app"), "--to", "16"]
        self.assertEqual(scan_json(argv), scan_json(argv))


if __name__ == "__main__":
    unittest.main()
