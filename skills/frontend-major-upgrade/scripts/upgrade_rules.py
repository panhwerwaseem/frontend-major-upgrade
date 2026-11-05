#!/usr/bin/env python3
"""Rule table for upgrade_scan.py, with a self-check.

Every breaking-change rule that upgrade_scan.py applies is plain data in RULES
below, so it can be audited without reading the scanner. Each rule names the
package whose major version governs it, the major that removed the API, a
regular expression, and examples the expression must and must not match.

Run this file to list the table or to test every pattern against its examples.

Examples:
  upgrade_rules.py                     # list every rule
  upgrade_rules.py --framework next    # rules that apply to a Next.js project
  upgrade_rules.py --check             # test each pattern against its examples
  upgrade_rules.py --json              # the table as JSON

Exit codes: 0 = listed, or every rule passed its examples; 1 = a rule failed
its own examples (--check); 2 = usage error.
Standard library only. Reads nothing. Runs nothing. Makes no network calls.
"""
import argparse
import json
import re
import sys

# The package whose major version defines the stages for each framework.
ANCHOR = {"react": "react", "next": "next", "angular": "@angular/core"}

# Packages whose majors are tracked for each framework (rules attach to these).
TRACKED = {
    "react": ["react"],
    "next": ["next", "react"],
    "angular": ["@angular/core", "@angular/material"],
}

# What a framework stage does to a tracked companion package. A number is the
# companion's major at that framework major; "same" means it follows the
# framework major. Next 15: the App Router needs React 19 (the Pages Router
# also runs on React 18). Majors missing from the map leave the companion alone.
COMPANIONS = {
    "next": {"react": {13: 18, 14: 18, 15: 19, 16: 19}},
    "angular": {"@angular/material": "same"},
}

# Packages that share a major with an anchor package. "break" = a mismatch is
# a peer-dependency conflict; "review" = expected to match, check it.
ANGULAR_FRAMEWORK = [
    "@angular/animations", "@angular/common", "@angular/compiler", "@angular/compiler-cli",
    "@angular/elements", "@angular/forms", "@angular/language-service", "@angular/localize",
    "@angular/platform-browser", "@angular/platform-browser-dynamic",
    "@angular/platform-server", "@angular/router", "@angular/service-worker", "@angular/upgrade",
]
LOCK_GROUPS = [
    {"anchor": "react", "members": ["react-dom", "react-test-renderer"], "level": "break",
     "why": "it peer-depends on the matching react release"},
    {"anchor": "react", "members": ["@types/react", "@types/react-dom"], "level": "review",
     "why": "the type packages follow the React major"},
    {"anchor": "next", "members": ["eslint-config-next", "@next/*"], "level": "review",
     "why": "it is published together with next under the same version"},
    {"anchor": "@angular/core", "members": ANGULAR_FRAMEWORK, "level": "break",
     "why": "Angular framework packages are released together and peer-depend on the same @angular/core"},
    {"anchor": "@angular/core", "members": ["@angular/cli"], "level": "review", "min_anchor": 6,
     "why": "the CLI major follows the framework major"},
    {"anchor": "@angular/material", "members": ["@angular/cdk"], "level": "break",
     "why": "@angular/material peer-depends on the matching @angular/cdk"},
]

# Official upgrade guides. "default" is used for majors without their own entry.
GUIDES = {
    "react": {
        17: "https://legacy.reactjs.org/blog/2020/10/20/react-v17.html",
        18: "https://react.dev/blog/2022/03/08/react-18-upgrade-guide",
        19: "https://react.dev/blog/2024/04/25/react-19-upgrade-guide",
        "default": "https://react.dev/blog",
    },
    "next": {"default": "https://nextjs.org/docs/app/guides/upgrading"},
    "angular": {"default": "https://angular.dev/update-guide"},
}

# Official codemod entry points. {major} is the stage's target major. Exact
# transform names change between releases: the tool's --help and the guide win.
CODEMODS = {
    "react": {
        19: [
            "npx codemod@latest react/19/migration-recipe   (recipe named in the React 19 upgrade guide)",
            "npx types-react-codemod@latest preset-19 <path>   (TypeScript projects)",
        ],
        "default": ["npx react-codemod <transform> <path>   (transform names: the react-codemod README)"],
    },
    "next": {"default": [
        "npx @next/codemod@latest <transform> <path>   (transform names: the Next.js codemods page)",
        "npx @next/codemod@latest upgrade <target>   (Next 15 tooling and later; see --help for targets)",
    ]},
    "angular": {"default": [
        "ng update @angular/core@{major} @angular/cli@{major}   (runs that major's migrations)",
        "ng update @angular/material@{major}   (only when Angular Material is installed)",
    ]},
}

# Facts about a stage that no pattern can find. Keys are "framework:major".
STAGE_NOTES = {
    "react:17": ["17 changes behaviour more than API: events are delegated to the root container "
                 "instead of document, event pooling is removed, and effect cleanup runs asynchronously."],
    "react:18": ["ReactDOM.render still works in 18 but keeps the app on React 17 behaviour; switching "
                 "to createRoot turns on automatic batching and the stricter StrictMode effect checks.",
                 "Internet Explorer is no longer supported.",
                 "@types/react 18 removes the implicit children prop from React.FC."],
    "react:19": ["Move to the latest react 18.3 first: it warns about the APIs that 19 removes.",
                 "19 requires the new JSX transform.",
                 "propTypes checks are ignored in 19; read the guide for the other behaviour changes."],
    "next:13": ["Needs React 18.2 or later.",
                "The app directory is optional. Leave pages/ where it is during the upgrade."],
    "next:14": ["Needs Node.js 18.17 or later."],
    "next:15": ["The App Router needs React 19; the Pages Router also runs on React 18.",
                "fetch requests, GET route handlers and the client router cache are no longer cached by default.",
                "cookies(), headers(), draftMode(), params and searchParams became asynchronous; "
                "synchronous access still works in 15 with a warning."],
    "next:16": ["Needs Node.js 20.9 or later.",
                "Turbopack is the default bundler; a custom webpack configuration needs a decision first.",
                "Synchronous access to the request APIs is removed."],
    "angular:9": ["Ivy becomes the default compiler and renderer."],
    "angular:13": ["View Engine is removed and Internet Explorer 11 is no longer supported."],
    "angular:16": ["The compatibility compiler (ngcc) is removed, so libraries published only in "
                   "View Engine format stop working."],
    "angular:17": ["Angular Material 17 removes the legacy (pre-MDC) components."],
    "angular:19": ["Components, directives and pipes are standalone by default; ng update adds "
                   "standalone: false to the existing NgModule-based ones."],
    "angular:*": ["Node.js, TypeScript and RxJS ranges change with the Angular major: check "
                  "https://angular.dev/reference/versions for this stage."],
}

# kind "removed": the matched code stops working at removed_in.
# kind "check":   the pattern cannot decide alone; a person or agent must look.
# where: "source" (JS/TS files), "scripts" (package.json scripts), "tsconfig".
# codemod True: the official upgrade guide lists a codemod for this change.
RULES = [
    # ---- React (package: react) ------------------------------------------
    {"id": "react-dom-render", "package": "react", "deprecated_in": 18, "removed_in": 19,
     "kind": "removed", "where": "source", "codemod": True, "title": "ReactDOM.render",
     "pattern": r"\bReactDOM\s*\.\s*render\s*\(|import\s*\{[^}]*\brender\b[^}]*\}\s*from\s*['\"]react-dom['\"]",
     "fix": "Use createRoot from react-dom/client: createRoot(container).render(element).",
     "match": ["ReactDOM.render(<App />, root);", "import { render } from 'react-dom';"],
     "no_match": ["root.render(<App />);", "import { render } from '@testing-library/react';",
                  "import { createRoot } from 'react-dom/client';"]},
    {"id": "react-dom-hydrate", "package": "react", "deprecated_in": 18, "removed_in": 19,
     "kind": "removed", "where": "source", "codemod": True, "title": "ReactDOM.hydrate",
     "pattern": r"\bReactDOM\s*\.\s*hydrate\s*\(|import\s*\{[^}]*\bhydrate\b[^}]*\}\s*from\s*['\"]react-dom['\"]",
     "fix": "Use hydrateRoot(container, element) from react-dom/client.",
     "match": ["ReactDOM.hydrate(<App />, root);", "import { hydrate } from \"react-dom\";"],
     "no_match": ["hydrateRoot(root, <App />);", "ReactDOM.hydrateRoot(root, <App />);"]},
    {"id": "react-dom-unmount", "package": "react", "deprecated_in": 18, "removed_in": 19,
     "kind": "removed", "where": "source", "title": "unmountComponentAtNode",
     "pattern": r"\bunmountComponentAtNode\b",
     "fix": "Keep the root returned by createRoot and call root.unmount().",
     "match": ["ReactDOM.unmountComponentAtNode(host);"],
     "no_match": ["root.unmount();"]},
    {"id": "react-find-dom-node", "package": "react", "removed_in": 19,
     "kind": "removed", "where": "source", "title": "findDOMNode",
     "pattern": r"\bfindDOMNode\s*\(",
     "fix": "Attach a ref to the DOM element you need and read ref.current.",
     "match": ["const node = ReactDOM.findDOMNode(this);"],
     "no_match": ["const node = this.nodeRef.current;"]},
    {"id": "react-string-ref", "package": "react", "removed_in": 19,
     "kind": "removed", "where": "source", "codemod": True, "title": "string refs",
     "pattern": r"(?<![\w$.-])ref=([\"'])[\w$]+\1|\bthis\.refs\b",
     "fix": "Use a callback ref, createRef or useRef.",
     "match": ["<input ref=\"query\" />", "this.refs.query.focus();"],
     "no_match": ["<input ref={this.inputRef} />", "<a href=\"about\">", "<div data-ref=\"x\">",
                  "const ref = 'main';"]},
    {"id": "react-legacy-context", "package": "react", "removed_in": 19,
     "kind": "removed", "where": "source", "title": "legacy context",
     "pattern": r"\b(?:childContextTypes|getChildContext|contextTypes)\b",
     "fix": "Move to createContext: a Provider replaces getChildContext; contextType, useContext "
            "or a Consumer replaces contextTypes.",
     "match": ["static childContextTypes = {", "getChildContext() {", "Button.contextTypes = {"],
     "no_match": ["static contextType = ThemeContext;", "const theme = useContext(ThemeContext);"]},
    {"id": "react-create-factory", "package": "react", "removed_in": 19,
     "kind": "removed", "where": "source", "title": "React.createFactory",
     "pattern": r"\bReact\s*\.\s*createFactory\s*\(|import\s*\{[^}]*\bcreateFactory\b[^}]*\}\s*from\s*['\"]react['\"]",
     "fix": "Use JSX or React.createElement.",
     "match": ["const button = React.createFactory('button');"],
     "no_match": ["const el = React.createElement('button');", "const make = createFactoryFor(x);"]},
    {"id": "react-render-subtree", "package": "react", "removed_in": 19,
     "kind": "removed", "where": "source", "title": "unstable_renderSubtreeIntoContainer",
     "pattern": r"\bunstable_renderSubtreeIntoContainer\b",
     "fix": "Use createPortal from react-dom.",
     "match": ["ReactDOM.unstable_renderSubtreeIntoContainer(this, el, host);"],
     "no_match": ["ReactDOM.createPortal(el, host);"]},
    {"id": "react-test-renderer-shallow", "package": "react", "removed_in": 19,
     "kind": "removed", "where": "source", "title": "react-test-renderer/shallow",
     "pattern": r"['\"]react-test-renderer/shallow['\"]",
     "fix": "Install react-shallow-renderer and import from it, or move the test to a DOM-rendering test library.",
     "match": ["import ShallowRenderer from 'react-test-renderer/shallow';"],
     "no_match": ["import renderer from 'react-test-renderer';"]},
    {"id": "react-dom-test-utils", "package": "react", "removed_in": 19,
     "kind": "check", "where": "source", "codemod": True, "title": "react-dom/test-utils",
     "pattern": r"['\"]react-dom/test-utils['\"]",
     "fix": "Import act from 'react'. The other helpers (Simulate, renderIntoDocument and the rest) "
            "were removed in 19: rewrite tests that use them against a DOM testing library.",
     "match": ["import { act } from 'react-dom/test-utils';"],
     "no_match": ["import { act } from 'react';"]},
    {"id": "react-function-default-props", "package": "react", "removed_in": 19,
     "kind": "check", "where": "source", "title": "defaultProps assigned to a component",
     "pattern": r"^[ \t]*[A-Z][\w$]*\.defaultProps\s*=",
     "fix": "React 19 ignores defaultProps on function components; class components keep it. If this "
            "is a function component, move the defaults into the parameter destructuring.",
     "match": ["Badge.defaultProps = { tone: 'info' };"],
     "no_match": ["  static defaultProps = { size: 'm' };", "options.defaultProps = {};"]},

    # ---- Next.js (package: next) -----------------------------------------
    {"id": "next-link-anchor-child", "package": "next", "removed_in": 13,
     "kind": "removed", "where": "source", "codemod": True, "title": "<a> child inside next/link",
     "requires": r"from\s*['\"]next/link['\"]",
     "pattern": r"<Link\b(?![^>]*\blegacyBehavior\b)[^>]*>\s*<a\b",
     "fix": "Remove the <a> child and put its props on <Link>, or add the legacyBehavior prop.",
     "match": ["<Link href=\"/about\"><a>About</a></Link>", "<Link href=\"/about\">\n  <a className=\"nav\">About</a>"],
     "no_match": ["<Link href=\"/about\">About</Link>", "<Link href=\"/about\" legacyBehavior><a>About</a></Link>",
                  "<Link href=\"/a\"><abbr>A</abbr></Link>"]},
    {"id": "next-future-image", "package": "next", "removed_in": 13,
     "kind": "removed", "where": "source", "codemod": True, "title": "next/future/image",
     "pattern": r"['\"]next/future/image['\"]",
     "fix": "Import from next/image: the component was renamed in 13.",
     "match": ["import Image from 'next/future/image';"],
     "no_match": ["import Image from 'next/image';"]},
    {"id": "next-image-import", "package": "next", "removed_in": 13,
     "kind": "check", "where": "source", "codemod": True, "title": "next/image changes meaning in 13",
     "pattern": r"['\"]next/image['\"]",
     "fix": "From 13, next/image is the component that used to be next/future/image, and the old one "
            "is next/legacy/image. Rename the import to next/legacy/image to keep behaviour unchanged.",
     "match": ["import Image from 'next/image';"],
     "no_match": ["import Image from 'next/legacy/image';", "import Image from 'next/future/image';"]},
    {"id": "next-export-script", "package": "next", "removed_in": 14,
     "kind": "removed", "where": "scripts", "title": "next export command",
     "pattern": r"\bnext\s+export\b",
     "fix": "Set output: 'export' in the Next.js config and drop the command; next build then writes out/.",
     "match": ["next build && next export"],
     "no_match": ["next build", "next-export-optimize-images"]},
    {"id": "next-font-package", "package": "next", "removed_in": 14,
     "kind": "removed", "where": "source", "codemod": True, "title": "@next/font package",
     "pattern": r"['\"]@next/font(?:/[\w-]+)?['\"]",
     "fix": "Import from the built-in next/font (same sub-paths) and remove the @next/font dependency.",
     "match": ["import { Inter } from '@next/font/google';"],
     "no_match": ["import { Inter } from 'next/font/google';"]},
    {"id": "next-og-image-response", "package": "next", "removed_in": 14,
     "kind": "removed", "where": "source", "codemod": True, "title": "ImageResponse from next/server",
     "pattern": r"import\s*\{[^}]*\bImageResponse\b[^}]*\}\s*from\s*['\"]next/server['\"]",
     "fix": "Import ImageResponse from next/og.",
     "match": ["import { ImageResponse } from 'next/server';", "import {\n  ImageResponse,\n  NextRequest,\n} from \"next/server\";"],
     "no_match": ["import { ImageResponse } from 'next/og';", "import { NextResponse } from 'next/server';"]},
    {"id": "next-experimental-edge", "package": "next", "removed_in": 15,
     "kind": "removed", "where": "source", "codemod": True, "title": "runtime 'experimental-edge'",
     "pattern": r"\bruntime\s*[:=]\s*['\"]experimental-edge['\"]",
     "fix": "Use 'edge'. Next 15 rejects the experimental-edge value.",
     "match": ["export const runtime = 'experimental-edge';", "export const config = { runtime: \"experimental-edge\" };"],
     "no_match": ["export const runtime = 'edge';", "export const runtime = 'nodejs';"]},
    {"id": "next-sync-request-api", "package": "next", "deprecated_in": 15, "removed_in": 16,
     "kind": "check", "where": "source", "codemod": True, "title": "synchronous cookies(), headers() or draftMode()",
     "requires": r"from\s*['\"]next/headers['\"]",
     "pattern": r"(?<!await\s)(?<![\w$.])(?:cookies|headers|draftMode)\s*\(\s*\)",
     "fix": "These calls return a promise from Next 15: await the call (the enclosing function must be "
            "async). params and searchParams changed the same way and are not detected by this rule.",
     "match": ["const theme = cookies().get('theme');", "const store = headers();"],
     "no_match": ["const store = await cookies();", "const ua = (await headers()).get('user-agent');",
                  "import { cookies } from 'next/headers';"]},
    {"id": "next-lint-script", "package": "next", "removed_in": 16,
     "kind": "removed", "where": "scripts", "title": "next lint command",
     "pattern": r"\bnext\s+lint\b",
     "fix": "Call ESLint (or your linter) directly from the script; next lint was removed in 16.",
     "match": ["next lint", "next lint --dir src"],
     "no_match": ["eslint .", "next build"]},
    {"id": "next-amp", "package": "next", "removed_in": 16,
     "kind": "removed", "where": "source", "title": "next/amp",
     "pattern": r"['\"]next/amp['\"]",
     "fix": "AMP support was removed in Next 16. Remove the AMP usage before this stage.",
     "match": ["import { useAmp } from 'next/amp';"],
     "no_match": ["import Image from 'next/image';"]},

    # ---- Angular ----------------------------------------------------------
    {"id": "angular-http-package", "package": "@angular/core", "removed_in": 8,
     "kind": "removed", "where": "source", "title": "@angular/http",
     "pattern": r"['\"]@angular/http['\"]",
     "fix": "Use HttpClient from @angular/common/http. The @angular/http package was removed in 8.",
     "match": ["import { Http } from '@angular/http';"],
     "no_match": ["import { HttpClient } from '@angular/common/http';"]},
    {"id": "angular-view-engine-opt-out", "package": "@angular/core", "removed_in": 13,
     "kind": "removed", "where": "tsconfig", "title": "enableIvy: false",
     "pattern": r"\"enableIvy\"\s*:\s*false",
     "fix": "Remove the option and get the build passing with Ivy first. View Engine is gone in 13.",
     "match": ["\"enableIvy\": false"],
     "no_match": ["\"enableIvy\": true", "\"strictTemplates\": false"]},
    {"id": "angular-entry-components", "package": "@angular/core", "deprecated_in": 9, "removed_in": 16,
     "kind": "removed", "where": "source", "title": "entryComponents",
     "pattern": r"\bentryComponents\s*:",
     "fix": "Delete the entryComponents array. Ivy has not needed it since Angular 9.",
     "match": ["  entryComponents: [ConfirmDialogComponent],"],
     "no_match": ["  declarations: [ConfirmDialogComponent],"]},
    {"id": "angular-material-legacy", "package": "@angular/material", "deprecated_in": 15, "removed_in": 17,
     "kind": "removed", "where": "source", "title": "@angular/material/legacy-* imports",
     "pattern": r"['\"]@angular/material/legacy-[\w-]+['\"]",
     "fix": "Move to the MDC-based components (the import path without legacy-). The Angular Material "
            "15 migration guide covers the schematic and the style changes.",
     "match": ["import { MatLegacyButtonModule } from '@angular/material/legacy-button';"],
     "no_match": ["import { MatButtonModule } from '@angular/material/button';"]},
]

REQUIRED_FIELDS = ("id", "package", "removed_in", "kind", "where", "title", "pattern", "fix",
                   "match", "no_match")


def rules_for(framework):
    """Rules whose governing package is tracked for the framework (None = all)."""
    if framework is None:
        return list(RULES)
    return [rule for rule in RULES if rule["package"] in TRACKED[framework]]


def check_rules(rules):
    """Return a list of problems: missing fields, bad patterns, failed examples."""
    problems = []
    seen = set()
    for rule in rules:
        label = rule.get("id", "(rule without id)")
        missing = [field for field in REQUIRED_FIELDS if field not in rule]
        if missing:
            problems.append("%s: missing %s" % (label, ", ".join(missing)))
            continue
        if label in seen:
            problems.append("%s: duplicate id" % label)
        seen.add(label)
        if rule["kind"] not in ("removed", "check") or rule["where"] not in ("source", "scripts", "tsconfig"):
            problems.append("%s: unknown kind or where" % label)
        if rule.get("deprecated_in") is not None and rule["deprecated_in"] >= rule["removed_in"]:
            problems.append("%s: deprecated_in must be below removed_in" % label)
        try:
            pattern = re.compile(rule["pattern"], re.M)
            if rule.get("requires"):
                re.compile(rule["requires"])
        except re.error as exc:
            problems.append("%s: pattern does not compile: %s" % (label, exc))
            continue
        if not rule["match"] or not rule["no_match"]:
            problems.append("%s: needs at least one match and one no_match example" % label)
        for example in rule["match"]:
            if not pattern.search(example):
                problems.append("%s: should match but does not: %r" % (label, example))
        for example in rule["no_match"]:
            if pattern.search(example):
                problems.append("%s: should not match but does: %r" % (label, example))
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--framework", choices=sorted(ANCHOR), help="only rules for this framework")
    parser.add_argument("--check", action="store_true",
                        help="test every pattern against its match and no_match examples")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args(argv)

    rules = rules_for(args.framework)
    problems = check_rules(rules) if args.check else []
    if args.json:
        print(json.dumps({"rules": rules, "problems": problems}, indent=2))
        return 1 if problems else 0
    if args.check:
        for problem in problems:
            print("FAIL " + problem)
        print("%d rule(s) checked, %d problem(s)" % (len(rules), len(problems)))
        return 1 if problems else 0
    for rule in rules:
        since = "deprecated in %s, " % rule["deprecated_in"] if rule.get("deprecated_in") else ""
        print("%-30s %-18s %sremoved in %s  [%s, %s]" % (
            rule["id"], rule["package"], since, rule["removed_in"], rule["kind"], rule["where"]))
        print("    %s: %s" % (rule["title"], rule["fix"]))
    print("%d rule(s). Patterns and examples: read RULES in this file, or use --json." % len(rules))
    return 0


if __name__ == "__main__":
    sys.exit(main())
