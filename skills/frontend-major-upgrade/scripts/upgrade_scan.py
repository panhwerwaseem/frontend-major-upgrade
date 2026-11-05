#!/usr/bin/env python3
"""Plan a React, Next.js or Angular major upgrade and list the code that breaks.

Reads package.json for the framework and its version, builds the path one
major at a time, and scans the sources for the patterns in upgrade_rules.py.
It also checks that the packages which must share a major do, and, when a
node_modules folder exists, that installed dependencies allow each stage's
major in their peer ranges.

A clean scan means none of the listed patterns were found. It is not proof
that the upgrade is safe: the build and tests at each stage are.

Examples:
  upgrade_scan.py --to 19                    # project in the current directory
  upgrade_scan.py apps/web --to 16 --json
  upgrade_scan.py . --from 17 --to 19        # start major given by hand
  upgrade_scan.py . --to 17 --framework angular --fail-on review

Exit codes: 0 = no finding at or above --fail-on (default: break),
1 = at least one such finding, 2 = usage or input error.
Standard library only. Reads files only. Runs nothing. Makes no network calls.
"""
import argparse
import json
import os
import re
import sys
from fnmatch import fnmatch
from pathlib import Path

import upgrade_rules as table

LEVELS = ("deprecated", "review", "break")
SOURCE_EXT = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts")
SKIP_DIRS = {"node_modules", ".git", ".next", ".angular", ".turbo", ".cache", ".vercel",
             "dist", "build", "out", "coverage", "__pycache__"}
MAX_FILE_BYTES = 2000000
DEP_SECTIONS = ("dependencies", "devDependencies", "peerDependencies")
TEXT_LINES_PER_RULE = 8


class InputError(Exception):
    """A problem with the project or the arguments; reported without a traceback."""


def read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise InputError("cannot read %s: %s" % (path, exc.strerror or exc))
    except ValueError as exc:
        raise InputError("%s is not valid JSON: %s" % (path, exc))
    if not isinstance(data, dict):
        raise InputError("%s: expected a JSON object" % path)
    return data


def parse_major(range_text):
    """Lowest major an npm range starts at. None when the range names no version:
    a dist-tag, '*', or a workspace, file, git or alias reference."""
    if not isinstance(range_text, str) or re.search(r"[:/]", range_text):
        return None
    majors = []
    for part in range_text.split("||"):
        match = re.match(r"\s*(?:[\^~=v]|>=?)?\s*v?(\d+)", part)
        if match:
            majors.append(int(match.group(1)))
    return min(majors) if majors else None


def range_admits(range_text, major):
    """True or False when an npm range clearly allows or excludes every release
    of `major`; None when the range is not one of the simple forms handled."""
    unsure = False
    for part in str(range_text).split("||"):
        part = re.sub(r"(>=|<=|>|<|=|\^|~)\s+", r"\1", part.strip())
        if part in ("", "*", "x", "X"):
            return True
        low, high = 0, None
        hyphen = re.match(r"^v?(\d+)[\w.*-]*\s+-\s+v?(\d+)[\w.*-]*$", part)
        if hyphen:
            low, high = int(hyphen.group(1)), int(hyphen.group(2))
        else:
            for token in part.split():
                match = re.match(r"^(\^|~|>=|<=|>|<|=)?v?(\d+)((?:\.(?:\d+|[xX*]))*)(?:-[\w.-]+)?$", token)
                if not match:
                    low = None
                    break
                op, number = match.group(1) or "", int(match.group(2))
                if op in (">=", ">"):
                    low = max(low, number)
                    continue
                if op == "<" and not re.sub(r"[.0]", "", match.group(3)):
                    number -= 1                      # "<19" and "<19.0.0" stop at 18
                elif op not in ("<", "<="):
                    low = max(low, number)           # ^N, ~N, N, N.x, =N: that major only
                high = number if high is None else min(high, number)
        if low is None:
            unsure = True
        elif low <= major and (high is None or major <= high):
            return True
    return None if unsure else False


def all_deps(pkg):
    """{name: (section, range)} over the dependency sections, first section wins."""
    found = {}
    for section in DEP_SECTIONS:
        entries = pkg.get(section)
        if isinstance(entries, dict):
            for name, value in entries.items():
                found.setdefault(name, (section, value))
    return found


def detect_major(project, deps, name):
    """Where a package stands: the installed version when node_modules has it,
    otherwise the range declared in package.json. None when it is not a dependency."""
    if name not in deps:
        return None
    section, declared = deps[name]
    manifest = Path(project).joinpath("node_modules", *name.split("/")) / "package.json"
    if manifest.is_file():
        try:
            version = read_json(manifest).get("version")
        except InputError:
            version = None
        if isinstance(version, str) and parse_major(version) is not None:
            return {"major": parse_major(version), "source": "installed",
                    "evidence": "node_modules/%s/package.json version \"%s\"" % (name, version)}
    return {"major": parse_major(declared), "source": "declared",
            "evidence": "package.json %s.%s \"%s\"" % (section, name, declared)}


def detect_framework(deps):
    present = [name for name in ("next", "angular", "react") if table.ANCHOR[name] in deps]
    if "next" in present:
        return "next"
    if len(present) == 1:
        return present[0]
    if not present:
        raise InputError("package.json lists none of react, next or @angular/core. In a "
                         "monorepo, point the script at the application package.")
    raise InputError("package.json lists both react and @angular/core; pass --framework.")


def build_stages(framework, start, target, majors):
    """One stage per framework major. `majors` holds the current major of every
    tracked package that is present; companions move as the table says."""
    anchor = table.ANCHOR[framework]
    have = dict(majors)
    have[anchor] = start
    stages = []
    for major in range(start + 1, target + 1):
        moves = {anchor: [have[anchor], major]}
        notes = table.STAGE_NOTES.get("%s:%d" % (framework, major), []) + \
            table.STAGE_NOTES.get("%s:*" % framework, [])
        for package, plan in sorted(table.COMPANIONS.get(framework, {}).items()):
            wanted = major if plan == "same" else plan.get(major)
            if wanted is None and package in have:
                notes = notes + ["The table does not say which %s major this stage needs: check the guide." % package]
            if have.get(package) is not None and wanted is not None and wanted > have[package]:
                moves[package] = [have[package], wanted]
        for package, (_, new) in moves.items():
            have[package] = new
        guides = table.GUIDES[framework]
        codemods = table.CODEMODS[framework]
        stages.append({
            "name": "%s %d -> %d" % (anchor, major - 1, major),
            "moves": moves,
            "guide": guides.get(major, guides["default"]),
            "codemods": [line.format(major=major) for line in codemods.get(major, codemods["default"])],
            "notes": notes,
            "rules_in_table": sum(1 for rule in table.RULES if rule["package"] in moves
                                  and moves[rule["package"]][0] < rule["removed_in"] <= moves[rule["package"]][1]),
            "move_together": [],
        })
    return stages, have


def plan_rules(stages, start_majors, final_majors):
    """{rule id: (level, stage index or None)} for the rules that apply on this path."""
    active = {}
    for rule in table.RULES:
        package = rule["package"]
        if start_majors.get(package) is None:
            continue
        for index, stage in enumerate(stages):
            low, high = stage["moves"].get(package, (0, 0))
            if low < rule["removed_in"] <= high:
                active[rule["id"]] = ("break" if rule["kind"] == "removed" else "review", index)
                break
        else:
            since = rule.get("deprecated_in")
            moved = final_majors[package] != start_majors[package]
            if since and moved and since <= final_majors[package] < rule["removed_in"]:
                active[rule["id"]] = ("deprecated", None)
    return active


def family_findings(deps, stages):
    """Check packages that must share a major, and fill each stage's move_together list."""
    findings, family = [], set()
    for group in table.LOCK_GROUPS:
        anchor = group["anchor"]
        if anchor not in deps:
            continue
        members = sorted(n for n in deps if n != anchor and any(fnmatch(n, p) for p in group["members"]))
        family.update([anchor] + members)
        for stage in stages:
            if anchor in stage["moves"]:
                stage["move_together"] = sorted(set(stage["move_together"]) | set([anchor] + members))
        anchor_major = parse_major(deps[anchor][1])
        if anchor_major is None or anchor_major < group.get("min_anchor", 0):
            continue
        for name in members:
            major = parse_major(deps[name][1])
            if major is not None and major != anchor_major:
                findings.append({
                    "level": group["level"], "rule": "family-mismatch", "stage": None,
                    "title": "%s is on major %d but %s is on %d" % (name, major, anchor, anchor_major),
                    "evidence": "package.json %s.%s" % (deps[name][0], name),
                    "detail": "\"%s\" (%s \"%s\")" % (deps[name][1], anchor, deps[anchor][1]),
                    "fix": "Align it with %s inside the current major before the first stage: %s." % (
                        anchor, group["why"]),
                })
    return findings, family


def peer_findings(project, deps, family, stages):
    """Installed direct dependencies whose peer range excludes a stage's major."""
    modules = Path(project) / "node_modules"
    if not modules.is_dir():
        return [], {"status": "skipped", "checked": 0, "not_understood": [],
                    "reason": "no node_modules folder, so peer ranges of installed dependencies were not checked"}
    findings, unsure, checked = [], [], 0
    for name in sorted(deps):
        manifest = modules.joinpath(*name.split("/")) / "package.json"
        if name in family or not manifest.is_file():
            continue
        try:
            data = read_json(manifest)
        except InputError:
            continue
        checked += 1
        peers = data.get("peerDependencies")
        for package in sorted(peers if isinstance(peers, dict) else {}):
            for index, stage in enumerate(stages):
                if package not in stage["moves"]:
                    continue
                verdict = range_admits(peers[package], stage["moves"][package][1])
                if verdict is None:
                    unsure.append("%s peerDependencies.%s \"%s\"" % (name, package, peers[package]))
                if verdict is False:
                    findings.append({
                        "level": "break", "rule": "peer-range", "stage": index,
                        "title": "%s %s does not allow %s %d" % (
                            name, data.get("version", "?"), package, stage["moves"][package][1]),
                        "evidence": "node_modules/%s/package.json peerDependencies.%s" % (name, package),
                        "detail": "\"%s\"" % peers[package],
                        "fix": "Find a release of %s that supports %s %d and upgrade it in this stage, "
                               "or replace it. Do not hide the conflict with --legacy-peer-deps or --force." % (
                                   name, package, stage["moves"][package][1]),
                    })
                if verdict is not True:
                    break
    return findings, {"status": "checked", "checked": checked, "not_understood": unsure, "reason": ""}


def strip_comments(text):
    """Blank out // and /* */ comments, keeping line numbers. Lexical, not a
    parser: it tracks quotes so that '//' inside a string or URL is kept."""
    if "//" not in text and "/*" not in text:
        return text
    out, i, size, quote = [], 0, len(text), None
    while i < size:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < size else ""
        if quote:
            if ch == "\\" and nxt:
                out.append(ch + nxt)
                i += 2
                continue
            if ch == quote or (ch == "\n" and quote != "`"):
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif ch == "/" and nxt in "/*" and nxt:
            if nxt == "/":
                end = text.find("\n", i)
                end = size if end == -1 else end
            else:
                end = text.find("*/", i + 2)
                end = size if end == -1 else end + 2
            out.append(re.sub(r"[^\n]", " ", text[i:end]))
            i = end
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def iter_files(project):
    """Yield (kind, path) for source and tsconfig files, in a stable order."""
    for root, dirs, files in os.walk(str(project)):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name.endswith(SOURCE_EXT) and not name.endswith(".min.js"):
                yield "source", Path(root) / name
            elif name.startswith("tsconfig") and name.endswith(".json"):
                yield "tsconfig", Path(root) / name


def rule_finding(rule, active, evidence, detail):
    level, stage = active[rule["id"]]
    return {"level": level, "rule": rule["id"], "stage": stage, "title": rule["title"],
            "evidence": evidence, "detail": detail, "fix": rule["fix"],
            "codemod": bool(rule.get("codemod")),
            "deprecated_in": rule.get("deprecated_in"), "removed_in": rule["removed_in"]}


def scan(project, pkg, active):
    """Apply the active rules to the sources and to package.json scripts."""
    compiled = [(rule, re.compile(rule["pattern"], re.M),
                 re.compile(rule["requires"]) if rule.get("requires") else None)
                for rule in table.RULES if rule["id"] in active]
    findings, stats = [], {"files_scanned": 0, "files_skipped": 0}
    for kind, path in iter_files(project):
        rules_here = [entry for entry in compiled if entry[0]["where"] == kind]
        try:
            raw = path.read_text(encoding="utf-8", errors="replace") if path.stat().st_size <= MAX_FILE_BYTES else None
        except OSError:
            raw = None
        if raw is None:
            stats["files_skipped"] += 1
            continue
        stats["files_scanned"] += 1
        text = strip_comments(raw) if rules_here else ""
        lines = raw.split("\n")
        relative = path.relative_to(project).as_posix()
        for rule, pattern, requires in rules_here:
            if requires and not requires.search(text):
                continue
            seen = set()
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                if line not in seen:
                    seen.add(line)
                    findings.append(rule_finding(
                        rule, active, "%s:%d" % (relative, line), lines[line - 1].strip()[:160]))
    scripts = pkg.get("scripts") if isinstance(pkg.get("scripts"), dict) else {}
    for rule, pattern, _ in compiled:
        for name in sorted(scripts if rule["where"] == "scripts" else {}):
            if isinstance(scripts[name], str) and pattern.search(scripts[name]):
                findings.append(rule_finding(
                    rule, active, "package.json scripts.%s" % name, scripts[name][:160]))
    return findings, stats


def evidence_key(evidence):
    """Sort 'file:9' before 'file:10'."""
    match = re.match(r"^(.*):(\d+)$", evidence)
    return (match.group(1), int(match.group(2))) if match else (evidence, 0)


def analyse(project, framework=None, start=None, target=None):
    project = Path(project)
    if not project.is_dir():
        raise InputError("%s is not a directory" % project)
    pkg = read_json(project / "package.json")
    deps = all_deps(pkg)
    framework = framework or detect_framework(deps)
    anchor = table.ANCHOR[framework]
    if anchor not in deps:
        raise InputError("--framework %s was given but package.json does not list %s" % (framework, anchor))
    found = {name: detect_major(project, deps, name) for name in table.TRACKED[framework]}
    majors = {name: info["major"] for name, info in found.items() if info}
    if start is None:
        start = majors[anchor]
    if start is None:
        raise InputError("cannot read a major version from %s; pass --from <major>" % found[anchor]["evidence"])
    if target < start:
        raise InputError("--to %d is below the current major %d; downgrades are not planned" % (target, start))
    majors[anchor] = start
    stages, final = build_stages(framework, start, target, majors)
    family, family_set = family_findings(deps, stages)
    active = plan_rules(stages, majors, final)
    peers, peer_check = peer_findings(project, deps, family_set, stages)
    matched, stats = scan(project, pkg, active)
    findings = family + peers + matched
    findings.sort(key=lambda f: (-1 if f["stage"] is None and f["level"] != "deprecated" else
                                 len(stages) if f["stage"] is None else f["stage"],
                                 -LEVELS.index(f["level"]), f["rule"], evidence_key(f["evidence"])))
    notes = []
    if deps[anchor][0] == "peerDependencies":
        notes.append("%s is a peerDependency here, so this looks like a library. The path assumes "
                     "you are raising the lowest supported major." % anchor)
    if found[anchor]["source"] == "declared":
        notes.append("Version read from the declared range, not from an installed package.")
    return {
        "project": str(project), "framework": framework, "package": anchor,
        "from": start, "to": target, "version_evidence": found[anchor]["evidence"],
        "notes": notes, "stages": stages, "findings": findings, "peer_check": peer_check,
        "summary": dict((level, sum(1 for f in findings if f["level"] == level)) for level in LEVELS),
        "files_scanned": stats["files_scanned"], "files_skipped": stats["files_skipped"],
    }


def render_findings(findings, out):
    groups = {}
    for finding in findings:
        groups.setdefault((finding["level"], finding["rule"], finding["title"]), []).append(finding)
    for (level, rule, title), items in groups.items():
        first = items[0]
        extra = "   (codemod listed in the upgrade guide)" if first.get("codemod") else ""
        if level == "deprecated":
            extra = "   (deprecated in %s, removed in %s)" % (first["deprecated_in"], first["removed_in"])
        out.append("  [%s] %s: %s%s" % (level, rule, title, extra))
        for item in items[:TEXT_LINES_PER_RULE]:
            out.append("      %s  %s" % (item["evidence"], item["detail"]))
        if len(items) > TEXT_LINES_PER_RULE:
            out.append("      ... and %d more (use --json for all)" % (len(items) - TEXT_LINES_PER_RULE))
        out.append("      fix: " + first["fix"])


def render(result):
    out = ["project: %s" % result["project"],
           "framework: %s   current: %s %d   target: %d" % (
               result["framework"], result["package"], result["from"], result["to"]),
           "version evidence: %s" % result["version_evidence"]]
    out.extend("note: " + note for note in result["notes"])
    stages, findings = result["stages"], result["findings"]
    if stages:
        out.append("path: %s (%d stage%s, one major each)" % (
            " -> ".join(str(n) for n in range(result["from"], result["to"] + 1)),
            len(stages), "" if len(stages) == 1 else "s"))
    else:
        out.append("Already on %s %d. No stages to plan." % (result["package"], result["to"]))
    before = [f for f in findings if f["stage"] is None and f["level"] != "deprecated"]
    if before:
        out.extend(["", "Before stage 1"])
        render_findings(before, out)
    for index, stage in enumerate(stages):
        others = ["%s %d -> %d" % (name, low, high) for name, (low, high) in sorted(stage["moves"].items())
                  if name != result["package"]]
        out.extend(["", "Stage %d: %s%s" % (index + 1, stage["name"],
                                            " (with %s)" % ", ".join(others) if others else "")])
        out.append("  move together: " + ", ".join(stage["move_together"] or sorted(stage["moves"])))
        out.append("  guide: " + stage["guide"])
        out.extend("  codemod: " + line for line in stage["codemods"])
        out.extend("  note: " + note for note in stage["notes"])
        here = [f for f in findings if f["stage"] == index]
        render_findings(here, out)
        if not here:
            out.append("  no findings (the rule table has %d rule(s) for this stage%s)" % (
                stage["rules_in_table"], "" if stage["rules_in_table"] else ": read the guide"))
    later = [f for f in findings if f["level"] == "deprecated"]
    if later:
        out.extend(["", "Deprecated at the target (still works there; removed in a later major)"])
        render_findings(later, out)
    peer = result["peer_check"]
    out.append("")
    if peer["status"] == "skipped":
        out.append("peer ranges: not checked (%s)" % peer["reason"])
    else:
        out.append("peer ranges: %d installed direct dependencies checked" % peer["checked"])
        out.extend("  not understood, check by hand: " + item for item in peer["not_understood"])
    summary = result["summary"]
    out.append("summary: %d break, %d review, %d deprecated; %d file(s) scanned%s" % (
        summary["break"], summary["review"], summary["deprecated"], result["files_scanned"],
        ", %d skipped (unreadable or over 2 MB)" % result["files_skipped"] if result["files_skipped"] else ""))
    out.append("A scan with no findings is not proof of a safe upgrade. Verify every stage with stage_ledger.py.")
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", nargs="?", default=".", help="folder that holds package.json (default: .)")
    parser.add_argument("--to", type=int, required=True, metavar="MAJOR", help="target major version")
    parser.add_argument("--from", type=int, dest="start", metavar="MAJOR",
                        help="starting major, when it cannot or should not be read from the project")
    parser.add_argument("--framework", choices=sorted(table.ANCHOR), help="override detection")
    parser.add_argument("--fail-on", choices=LEVELS, default="break",
                        help="lowest level that makes the exit code 1 (default: break)")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args(argv)
    try:
        result = analyse(args.project, args.framework, args.start, args.to)
    except InputError as exc:
        print("upgrade_scan.py: error: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else render(result))
    blocking = LEVELS[LEVELS.index(args.fail_on):]
    return 1 if any(f["level"] in blocking for f in result["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
