---
name: frontend-major-upgrade
description: Runs a React, Next.js or Angular major-version upgrade one major at a time, codemods first, with a recorded build and test result at every stage. Use when the user asks to upgrade, bump or migrate React, Next.js or Angular to a new major version (for example React 17 to 19, Next 13 to 15, Angular 15 to 17), when a major framework bump has broken the build or tests, when removed APIs such as ReactDOM.render, string refs or findDOMNode must be found before an upgrade, or when the user mentions a codemod, ng update, or peer dependency conflicts after a framework bump.
license: MIT
compatibility: Requires Python 3.9 or later to run the bundled scripts. No network access and no extra packages needed. The upgrade itself needs the project's own package manager, which the agent runs, not the scripts.
metadata:
  author: panhwerwaseem
  version: "0.1.0"
---

# Frontend major upgrade

A major upgrade is done when three things are true: the project is on the
target major, every stage on the way there passed the same build and test
checks that passed before the upgrade started, and the report says what was
changed by codemod, what by hand, and what is left. Everything below serves
those three conditions.

Paths in this file are relative to this skill's directory.

## Hard rules

1. **Green baseline first.** Do not change a version until
   `scripts/stage_ledger.py` has recorded passing checks on the current
   version. If the baseline is red, stop and tell the user. Do not start an
   upgrade on a broken build, and do not repair unrelated failures unasked.
2. **One major at a time.** Never move a framework across more than one major
   in a single step, whatever the user's deadline. The stages are the ones
   `scripts/upgrade_scan.py` prints.
3. **Codemods before hand edits.** In each stage, run the official codemod or
   `ng update` first and keep its output as its own commit. Hand-edit only what
   the codemod left. Do not hand-write a change that a codemod makes.
4. **The family moves together.** Packages listed under "move together" change
   in the same stage as the framework. Do not silence a peer-dependency
   conflict with `--legacy-peer-deps`, `--force` or an override unless the user
   agrees, and then name it in the report.
5. **No refactors inside the upgrade.** Change only what the new major
   requires. Do not convert classes to hooks, `pages/` to `app/`, NgModules to
   standalone, or adopt new APIs, rename, or reformat. List those as follow-ups.
6. **Never advance past a failing stage.** A stage is passed only when
   `stage_ledger.py advance` accepts it. Do not make a check pass by skipping
   or deleting tests, narrowing the command, updating snapshots without
   reading them, or adding `any`, `@ts-ignore` or lint disables.
7. **A clean scan is not proof.** The scanner knows a short list of patterns.
   Claim a stage works only on the ledger's evidence, never on "no findings".

## Workflow

### 1. Fix the target and plan the path

Get the target major from the user. If they said "latest", find the latest
stable major yourself (for example `npm view <package> dist-tags.latest`); the
scripts do not look it up. Then:

```bash
python3 scripts/upgrade_scan.py <project folder> --to <target major>
```

The output gives the detected framework and version with its evidence, the
stages (one major each), the packages that move together in each stage, the
official guide and codemod entry point per stage, and findings with file and
line. Levels: `break` stops working at that stage, `review` needs a person to
decide, `deprecated` still works at the target. Show the user the path and the
`break` count before changing anything.

If dependencies are installed, the scan also checks the peer ranges of
installed direct dependencies. If it says peer ranges were not checked, install
dependencies and run it again before planning.

### 2. Record the baseline

```bash
python3 scripts/stage_ledger.py start --package <react|next|@angular/core> --from <current> --to <target>
python3 scripts/stage_ledger.py verify --check build -- <build command>
python3 scripts/stage_ledger.py verify --check test -- <test command>
python3 scripts/stage_ledger.py advance
```

Use the commands CI uses, in non-watch mode. Add a check for each thing the
project relies on (`typecheck`, `lint`, `e2e`). Every check that passes here
must be run again at every stage, so do not add one you cannot keep. Run the
scripts from the project root so the ledger lands in the project's
`.frontend-upgrade/` folder, or pass `--ledger` and `--project`.

Findings under "Before stage 1" are packages on the wrong major today. Align
them inside the current major, re-run the baseline checks, then advance.

### 3. Run each stage

Repeat for every stage, in order. `references/staged-method.md` has the detail.

1. **Bump the family.** Move the framework and every "move together" package
   to this stage's major, and install. For Angular, `ng update` does this and
   the migrations together.
2. **Run the codemod** named for the stage (`references/codemods.md`). Start
   from a clean working tree, read the diff, commit it alone, and record it:
   `python3 scripts/stage_ledger.py note "<what ran, how many files changed>"`.
3. **Re-scan** to see what the codemod left:
   `python3 scripts/upgrade_scan.py <project> --from <previous major> --to <stage major>`.
4. **Hand-edit** the remaining `break` findings, then decide each `review`
   finding. `references/breaking-changes.md` lists what each rule means and
   the behaviour changes no pattern can find.
5. **Verify** with the same commands as the baseline:
   `python3 scripts/stage_ledger.py verify --check <name> -- <command>` for
   each check. A failing check prints the tail of its log. Fix the cause and
   re-run. If the ledger prints that a command differs from the baseline,
   either restore the command or explain the change in the report.
6. **Advance:** `python3 scripts/stage_ledger.py advance`. If it is refused,
   the stage is not done. Commit the stage before starting the next one.

`verify` refuses to run when the installed version is not the stage's major.
That is the guard against skipping a major or verifying before installing.

### 4. When a stage will not go green

Stop at that stage. Do not start the next one, and do not weaken a check. Tell
the user which check fails, the evidence from the log, what you tried, and the
options: fix the cause, replace or upgrade the blocking dependency, or ship the
upgrade up to the last passed stage. The ledger keeps the state, so the work
can resume later with `python3 scripts/stage_ledger.py status`.

### 5. Report

Fill this in from the scan and the ledger:

```
Upgrade:      <package> <from> -> <to>   (reached: <major the project is on now>)
Baseline:     <checks and commands>, all passing before any change
Stages:
  <a> -> <b>  codemod: <what ran> | by hand: <files or count> | checks: <names, attempts> | <passed or OPEN>
  ...
Family:       <packages moved with the framework; dependencies upgraded or replaced for peer ranges>
Suppressed:   <peer conflicts silenced, checks whose command changed, tests skipped> or "none"
Review items: <each review finding and the decision taken>
Not done:     <stages not reached, deprecated APIs left in place, refactors deliberately not made>
Evidence:     .frontend-upgrade/ledger.json and its logs
```

## Edge cases

- **Version cannot be read** (`latest`, `workspace:*`, a git URL). Pass
  `--from <major>` to the scan after checking what is installed.
- **Monorepo.** Run the scan and keep a ledger per application package. Shared
  packages that several apps consume move in the stage of the first app, and
  every consuming app must then pass its checks.
- **Library, not an application.** When the framework is a `peerDependency`,
  the job is widening or raising the supported range. Test against each
  supported major; say so in the report.
- **Next.js on the Pages Router.** Next 15 accepts React 18 there. Keeping
  React 18 is allowed only if the user chooses it; the scan assumes React 19.
- **No tests.** Say so before starting. The baseline is then build, type-check
  and whatever smoke check the user accepts, and the report must state that
  the upgrade was verified without tests.
- **A dependency has no release for the new major.** That blocks the stage.
  Offer replacing it, waiting, or stopping one stage earlier. Do not force it.
- **Pre-release target** (canary, RC). Ask first; guides and codemods may not
  match yet.
- **`.frontend-upgrade/`** holds the ledger and check logs. Add it to
  `.gitignore`, or commit it if the team wants the evidence in the branch.
