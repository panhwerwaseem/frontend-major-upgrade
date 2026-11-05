# The staged method

How to run one stage of a major upgrade, and why each step is there. The
workflow in `SKILL.md` is the short form; this file is the detail.

## Contents

- [Why one major at a time](#why-one-major-at-a-time)
- [Before the first stage](#before-the-first-stage)
- [Inside one stage](#inside-one-stage)
- [What counts as verification](#what-counts-as-verification)
- [The family and its peers](#the-family-and-its-peers)
- [What is not part of the upgrade](#what-is-not-part-of-the-upgrade)
- [When a stage fails](#when-a-stage-fails)
- [Commits and rollback](#commits-and-rollback)

## Why one major at a time

- Each major's upgrade guide and codemods assume you start from the previous
  major. A codemod written for 18 to 19 does not know about changes made
  in 17.
- Deprecation warnings are the framework's own migration list. They appear in
  the major before an API is removed. Skip that major and you skip the list.
- When a check fails after a single-major step, the cause is in one guide. When
  it fails after a three-major jump, it could be in any of three.
- Angular's `ng update` moves one major at a time; the Angular update guide
  says to update across several majors in separate steps.

## Before the first stage

1. **Working tree clean, on a branch.** Codemods rewrite many files. You need
   to see exactly what they changed.
2. **Baseline recorded.** Build and tests pass on the current version, with the
   commands CI uses, recorded with `scripts/stage_ledger.py`. A check that is
   already failing must be fixed or explicitly excluded by the user before the
   upgrade starts; otherwise nobody can tell a regression from an old failure.
3. **Latest release of the current major.** Move to the newest minor of the
   major you are on and run the checks. This is a small step that surfaces the
   deprecation warnings written for the next major. For React 18 to 19 the
   React team published 18.3 for this purpose.
4. **Clear the warnings you can.** Fix deprecation warnings from the framework
   while still on the current major, where the old and the new API both work.
   Each one fixed here is one less failure in the next stage.
5. **Family aligned.** Fix every "Before stage 1" finding from
   `scripts/upgrade_scan.py`: packages that should share the framework's major
   and do not.

## Inside one stage

Order matters. Each step produces something the next one needs.

| Step | Action | Evidence it leaves |
|---|---|---|
| 1 | Bump the framework and its family to this stage's major; install | Lockfile diff; installed version |
| 2 | Run the official codemod for this major | A commit that contains only codemod output |
| 3 | Re-scan with `upgrade_scan.py --from <previous> --to <this>` | The list the codemod did not handle |
| 4 | Hand-edit the remaining `break` findings; decide the `review` findings | A second, smaller commit |
| 5 | Run every baseline check through `stage_ledger.py verify` | Ledger entries and logs |
| 6 | `stage_ledger.py advance` | The stage marked passed |

Notes on the steps:

- **Step 1.** Use the project's package manager and lockfile. Do not delete the
  lockfile to "get a clean install": that upgrades every transitive dependency
  at once and hides which change broke what.
- **Step 2.** If the codemod asks which transforms to run, choose the ones the
  guide lists for this major only. Read the diff. A codemod can produce code
  that compiles and is wrong, for example by wrapping a value it could not
  analyse.
- **Step 3.** After the bump the installed version is already the new major,
  so pass `--from` with the previous major or the scan reports nothing to do.
- **Step 4.** Fix what the new major requires and nothing else. If a `review`
  finding turns out not to apply (for example `defaultProps` on a class
  component), say so in the report instead of leaving it unexplained.
- **Step 5.** Same commands as the baseline. Read new warnings in the output:
  a stage can pass its tests and still print the next major's deprecations.

## What counts as verification

A stage is verified by commands that exit non-zero on failure and that were
passing at baseline:

- the production build
- the type-check, when the project uses TypeScript
- the unit and component tests, in non-watch mode
- the linter, when CI runs it
- end-to-end or smoke tests, when they exist

These do not count as verification: the dev server starting, "it compiles",
a scan with no findings, or a subset of the tests chosen after a failure.

Things that weaken a check, and are therefore not fixes: skipping or deleting a
failing test, updating snapshots without reading the difference, adding
`any`, `@ts-ignore`, `@ts-expect-error` or a lint disable to silence a new
error, raising a timeout, or changing the test command. The ledger flags a
command that differs from the baseline so the change has to be explained.

When a test fails after an upgrade, decide which of these it is before editing:

| Case | What to do |
|---|---|
| The test relied on a removed API or on test tooling that no longer exists | Port the test to the supported API; keep what it asserts |
| The test asserted an implementation detail that legitimately changed | Update the assertion; say which detail and why it is not a regression |
| The product behaviour changed | That is a regression. Fix the product code or stop the stage |

## The family and its peers

Three groups of packages are tied to the framework's major:

1. **The family**: packages released with the framework (`react-dom` with
   `react`; every `@angular/*` framework package with `@angular/core`;
   `eslint-config-next` with `next`). They move in the same stage. The scan
   lists them under "move together".
2. **Tooling tied to the major**: type packages, the CLI, test renderers,
   and for Angular the TypeScript, Node.js and RxJS ranges. Check the
   framework's version table for the stage.
3. **Third-party libraries with a peer range** on the framework (UI kits,
   routers, state and form libraries, test libraries). The scan reads the
   peer ranges of installed direct dependencies and reports the stage each one
   blocks. For each blocker, look for a release that supports the new major
   and upgrade it in that stage.

A peer conflict reported by the package manager is information, not noise.
`--legacy-peer-deps` and `--force` in npm make the install succeed without
making the library work. Use them only with the user's agreement, record
which package was forced, and treat the stage as carrying a known risk.

## What is not part of the upgrade

An upgrade is a change of version with the smallest code change that keeps
behaviour the same. These are separate pieces of work, each with its own
review and its own risk:

| Tempting during the upgrade | Why it waits |
|---|---|
| Class components to function components and hooks | Not required by any React major |
| Next.js `pages/` to `app/` | The App Router is optional; both run side by side |
| NgModules to standalone components, or to the new control flow | Optional migrations with their own schematics |
| Adopting new APIs the major introduced | New behaviour hides upgrade regressions |
| Replacing the build tool or the test runner | A different migration |
| Reformatting, renaming, moving files | Makes the upgrade diff unreadable |

Exception: when the new major removes something and the only replacement is a
new API, using that API is the upgrade. Keep it to the files that need it.

List the opportunities you noticed under "Not done" in the report.

## When a stage fails

1. Read the failing check's log (`.frontend-upgrade/<stage>-<check>.log`).
2. Find the entry in the stage's upgrade guide that explains it. Most
   failures after a major bump are documented breaking changes.
3. If the cause is a third-party library, check its peer range and changelog
   before touching your own code.
4. Fix the cause and re-run the same check.
5. If it cannot be made green in the agreed time, stop. Report the stage as
   open, with the failing check and what was tried. The stages already passed
   are a valid, shippable upgrade to that major.

Do not continue to the next major "to see if it gets better". Failures stack,
and the ledger will refuse to advance.

## Commits and rollback

Keep each stage as its own commits, in this order: version bump and lockfile,
codemod output, hand edits. A reviewer can then skim the mechanical commit and
read the hand edits closely, and a failed stage can be reverted without losing
the stages before it. Deploying after each passed stage, where the team's
process allows it, catches runtime-only regressions one major at a time.
