#!/usr/bin/env python3
"""Record each stage of a major upgrade with its verification results, and
refuse to move on from a stage that has not passed.

The ledger is a JSON file with one entry per stage: a baseline on the starting
major, then one stage per major. Each stage holds named checks (build, test,
lint and so on). A check is recorded by running the command you give after
"--", directly and without a shell, and storing its exit code and log.

  start    create the ledger for a package and a path
  verify   run one check for the current stage and record the result
  advance  close the current stage and open the next; refused unless every
           check passed and every check that passed at baseline was run again
  note     attach a line of text to the current stage (codemods run, decisions)
  status   print the ledger

Before running a check, verify compares the version in the project with the
major the stage expects (baseline: the starting major). It reads the installed
package when node_modules has it, otherwise the range in package.json.

Examples:
  stage_ledger.py start --package react --from 17 --to 19
  stage_ledger.py verify --check build -- npm run build
  stage_ledger.py verify --check test -- npm test
  stage_ledger.py advance
  stage_ledger.py note "ran the React 19 migration recipe, 14 files changed"
  stage_ledger.py status --json

Exit codes: 0 = recorded a pass, advanced, or nothing is failing;
1 = the check failed, the stage's version is wrong, or advance was refused;
2 = usage or input error.
Standard library only. Makes no network calls. Writes only the ledger file and
check logs in the ledger's folder.
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import upgrade_scan

DEFAULT_LEDGER = ".frontend-upgrade/ledger.json"
CHECK_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
TAIL_LINES = 20


class LedgerError(Exception):
    """A usage or input problem; reported without a traceback, exit code 2."""


def new_ledger(package, start, target):
    stages = [{"name": "baseline", "major": start, "status": "open", "checks": {}, "notes": []}]
    for major in range(start + 1, target + 1):
        stages.append({"name": "%d -> %d" % (major - 1, major), "major": major,
                       "status": "pending", "checks": {}, "notes": []})
    return {"version": 1, "package": package, "from": start, "to": target,
            "current": 0, "complete": False, "stages": stages}


def load(path):
    if not path.is_file():
        raise LedgerError("no ledger at %s; run 'stage_ledger.py start' first" % path)
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
        ledger["stages"][ledger["current"] if not ledger["complete"] else 0]["checks"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LedgerError("%s is not a ledger written by this script (%s)" % (path, exc))
    return ledger


def save(path, ledger):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


def current_stage(ledger):
    if ledger["complete"]:
        raise LedgerError("the ledger is complete: every stage has passed")
    return ledger["stages"][ledger["current"]]


def version_problem(ledger, stage, project):
    """Return (evidence, problem). problem is None when the project is on the
    major this stage expects."""
    try:
        deps = upgrade_scan.all_deps(upgrade_scan.read_json(Path(project) / "package.json"))
    except upgrade_scan.InputError as exc:
        raise LedgerError("%s (pass --project, or --skip-version-check)" % exc)
    found = upgrade_scan.detect_major(project, deps, ledger["package"])
    if found is None:
        raise LedgerError("package.json in %s does not list %s" % (project, ledger["package"]))
    if found["major"] is None:
        return found["evidence"], "no major version can be read from %s" % found["evidence"]
    if found["major"] != stage["major"]:
        hint = ("Restore the starting version before recording the baseline."
                if stage["name"] == "baseline" else "Do this stage's upgrade and install first.")
        return found["evidence"], "stage '%s' expects %s %d, but %s. %s" % (
            stage["name"], ledger["package"], stage["major"], found["evidence"], hint)
    return found["evidence"], None


def run_check(command, cwd, timeout):
    started = time.time()
    try:
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=timeout, cwd=cwd)
        output = proc.stdout.decode("utf-8", errors="replace")
        status, exit_code = ("pass" if proc.returncode == 0 else "fail"), proc.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"").decode("utf-8", errors="replace")
        status, exit_code = "timeout", None
    except OSError as exc:
        raise LedgerError("cannot run %s: %s" % (command[0], exc.strerror or exc))
    return status, exit_code, round(time.time() - started, 1), output


def cmd_start(args, path):
    if path.exists() and not args.force:
        raise LedgerError("%s already exists; use 'status', or --force to start over" % path)
    if args.start < 0 or args.to <= args.start:
        raise LedgerError("--to must be above --from")
    ledger = new_ledger(args.package, args.start, args.to)
    save(path, ledger)
    return ledger, 0, ["Started: %d stage(s) after the baseline. Record the baseline checks with "
                       "'verify', then 'advance'." % (len(ledger["stages"]) - 1)]


def cmd_verify(args, path):
    ledger = load(path)
    stage = current_stage(ledger)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise LedgerError("give the verification command after --")
    if not CHECK_NAME_RE.match(args.check):
        raise LedgerError("--check must be lower-case letters, digits, '-' or '_'")
    if args.skip_version_check:
        evidence = "not checked (--skip-version-check)"
    else:
        evidence, problem = version_problem(ledger, stage, args.project)
        if problem:
            return ledger, 1, ["REFUSED: " + problem, "Nothing was run or recorded."]
    status, exit_code, duration, output = run_check(command, args.project, args.timeout)
    log_name = "%s-%s.log" % (stage["name"].replace(" -> ", "-to-"), args.check)
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / log_name).write_text(output, encoding="utf-8")
    baseline = ledger["stages"][0]["checks"].get(args.check)
    previous = stage["checks"].get(args.check, {})
    stage["checks"][args.check] = {
        "status": status, "exit_code": exit_code, "command": command, "duration_s": duration,
        "log": log_name, "attempts": previous.get("attempts", 0) + 1, "version_evidence": evidence,
        "differs_from_baseline": bool(ledger["current"] and baseline and baseline["command"] != command),
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    save(path, ledger)
    lines = ["%s: %s %s (%s, attempt %d, %.1fs)" % (
        stage["name"], args.check, status.upper(),
        "exit %s" % exit_code if exit_code is not None else "killed after %ss" % args.timeout,
        stage["checks"][args.check]["attempts"], duration)]
    if stage["checks"][args.check]["differs_from_baseline"]:
        lines.append("NOTE: this command differs from the baseline '%s' command: %s. Say so in the report."
                     % (args.check, " ".join(baseline["command"])))
    if status != "pass":
        lines.extend("    " + line for line in output.splitlines()[-TAIL_LINES:])
        lines.append("log: %s" % (path.parent / log_name))
    return ledger, (0 if status == "pass" else 1), lines


def advance_blockers(ledger, stage):
    blockers = []
    if not stage["checks"]:
        blockers.append("no check has been recorded for this stage")
    for name in sorted(stage["checks"]):
        if stage["checks"][name]["status"] != "pass":
            blockers.append("check '%s' last result is %s" % (name, stage["checks"][name]["status"]))
    if ledger["current"]:
        for name in sorted(ledger["stages"][0]["checks"]):
            if name not in stage["checks"]:
                blockers.append("check '%s' passed at baseline but has not been run for this stage" % name)
    return blockers


def cmd_advance(args, path):
    ledger = load(path)
    stage = current_stage(ledger)
    blockers = advance_blockers(ledger, stage)
    if blockers:
        return ledger, 1, ["REFUSED to advance past '%s':" % stage["name"]] + \
            ["  - " + reason for reason in blockers]
    stage["status"] = "passed"
    ledger["current"] += 1
    if ledger["current"] == len(ledger["stages"]):
        ledger["complete"] = True
        lines = ["'%s' passed. Every stage is verified: %s is on %d." % (
            stage["name"], ledger["package"], ledger["to"])]
    else:
        following = ledger["stages"][ledger["current"]]
        following["status"] = "open"
        lines = ["'%s' passed. Now open: '%s' (%s %d)." % (
            stage["name"], following["name"], ledger["package"], following["major"])]
    save(path, ledger)
    return ledger, 0, lines


def cmd_note(args, path):
    ledger = load(path)
    stage = current_stage(ledger)
    stage["notes"].append(args.text)
    save(path, ledger)
    return ledger, 0, ["noted on '%s'" % stage["name"]]


def cmd_status(args, path):
    ledger = load(path)
    lines = ["ledger: %s" % path,
             "package: %s   path: %d -> %d   %s" % (
                 ledger["package"], ledger["from"], ledger["to"],
                 "complete" if ledger["complete"] else
                 "current stage: %s" % ledger["stages"][ledger["current"]]["name"])]
    failing = False
    for index, stage in enumerate(ledger["stages"]):
        checks = []
        for name in sorted(stage["checks"]):
            check = stage["checks"][name]
            text = "%s %s" % (name, "pass" if check["status"] == "pass" else check["status"].upper())
            if check["attempts"] > 1:
                text += " (attempt %d)" % check["attempts"]
            if check["differs_from_baseline"]:
                text += " (command differs from baseline)"
            checks.append(text)
            failing = failing or (index == ledger["current"] and check["status"] != "pass")
        lines.append("  %-10s %-8s %s" % (stage["name"], stage["status"], ", ".join(checks) or "-"))
        lines.extend("             note: " + note for note in stage["notes"])
    if failing:
        lines.append("A check is failing on the current stage. Fix it and re-run verify; "
                     "advance is refused until every check passes.")
    return ledger, (1 if failing else 0), lines


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ledger", default=DEFAULT_LEDGER, help="ledger file (default: %s)" % DEFAULT_LEDGER)
    common.add_argument("--json", action="store_true", help="print the ledger as JSON")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="action", metavar="{start,verify,advance,note,status}")
    start = commands.add_parser("start", parents=[common], help="create the ledger")
    start.add_argument("--package", required=True, help="package that defines the stages, e.g. react")
    start.add_argument("--from", type=int, required=True, dest="start", metavar="MAJOR")
    start.add_argument("--to", type=int, required=True, metavar="MAJOR")
    start.add_argument("--force", action="store_true", help="overwrite an existing ledger")
    verify = commands.add_parser("verify", parents=[common], help="run and record one check")
    verify.add_argument("--check", required=True, metavar="NAME", help="name of the check, e.g. build or test")
    verify.add_argument("--project", default=".", help="folder with package.json; the command runs here")
    verify.add_argument("--timeout", type=float, default=1800.0, help="seconds before the command is killed")
    verify.add_argument("--skip-version-check", action="store_true",
                        help="do not compare the project's version with the stage (recorded in the ledger)")
    verify.add_argument("command", nargs=argparse.REMAINDER, help="the verification command, after --")
    commands.add_parser("advance", parents=[common], help="close the current stage")
    note = commands.add_parser("note", parents=[common], help="attach text to the current stage")
    note.add_argument("text")
    commands.add_parser("status", parents=[common], help="print the ledger")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.action:
        parser.error("choose one of: start, verify, advance, note, status")
    handler = {"start": cmd_start, "verify": cmd_verify, "advance": cmd_advance,
               "note": cmd_note, "status": cmd_status}[args.action]
    try:
        ledger, code, lines = handler(args, Path(args.ledger))
    except LedgerError as exc:
        print("stage_ledger.py: error: %s" % exc, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"exit_code": code, "messages": lines, "ledger": ledger}, indent=2))
    else:
        print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
