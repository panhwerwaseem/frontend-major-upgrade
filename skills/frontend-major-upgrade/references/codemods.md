# Codemods

The official migration tools for each framework and how to use them safely.
Transform names and flags change between releases. This file names each tool
and its entry point; the tool's own `--help` and the upgrade guide for the
major are the authority on exact transform names.

## Rules for any codemod

1. **Clean working tree first.** Commit or stash everything. The codemod's
   diff must contain only the codemod's changes.
2. **One major's codemods per stage.** Do not run the transforms for 19 while
   the project is still on 17.
3. **After the version bump, before hand edits.** Some transforms read the
   installed version or types.
4. **Read the diff.** Codemods work on syntax. Check for code that was moved
   into the wrong place, comments left where the tool gave up, and files it
   skipped because of a parse error (the tool's summary lists them).
5. **Commit the output alone**, then record it:
   `python3 scripts/stage_ledger.py note "<tool and transform>, <n> files changed"`.
6. **Re-scan.** `python3 scripts/upgrade_scan.py <project> --from <previous> --to <stage>`
   shows what is left for hand edits.
7. **A codemod is not verification.** Run the stage's checks through the
   ledger afterwards, as for any other change.

Running a codemod downloads and executes a package from the npm registry.
Check the package name against the upgrade guide before running it.

## React

| Tool | Use it for | Entry point |
|---|---|---|
| `codemod` (recipes named in the React 19 upgrade guide) | The React 19 migration | `npx codemod@latest react/19/migration-recipe` |
| `types-react-codemod` | TypeScript type changes in 18 and 19 | `npx types-react-codemod@latest preset-19 <path>` |
| `react-codemod` | Older migrations | `npx react-codemod <transform> <path>` |

- The React 19 upgrade guide lists the recipe and the single transforms it
  contains (for `ReactDOM.render`, string refs, the `act` import and others).
  Confirm the names there; if a name is rejected, the guide or the tool's
  help has the current one.
- `react-codemod` is the React team's older collection. Its README lists the
  transforms, including one that renames the unsafe lifecycle methods.
- Plan `findDOMNode` and legacy context as hand edits. Each use needs a
  decision about which element or which context value the component needs.

## Next.js

| Tool | Use it for | Entry point |
|---|---|---|
| `@next/codemod` | A single transform | `npx @next/codemod@latest <transform> <path>` |
| `@next/codemod` `upgrade` command | Bumping `next`, `react` and `react-dom` and running that version's transforms | `npx @next/codemod@latest upgrade <target>` |

- The codemods page in the Next.js documentation lists every transform under
  the version it belongs to. Run only the ones under this stage's version.
- The `upgrade` command arrived with the Next 15 tooling. Run it with
  `--help` to see the targets it accepts, and choose this stage's major, not
  the final one.
- The asynchronous request API transform cannot rewrite every case. It leaves
  a comment where a person has to decide; search the diff for those.

## Angular

| Tool | Use it for | Entry point |
|---|---|---|
| Angular CLI `ng update` | Bumping the framework and running that major's migrations | `ng update @angular/core@<major> @angular/cli@<major>` |
| Angular CLI `ng update` | Angular Material and the CDK | `ng update @angular/material@<major>` |

- `ng update` with no arguments lists the packages that have an update.
- It moves one major at a time. Run it once per stage with that stage's major.
- It refuses to run on a dirty working tree unless told otherwise. Keep the
  tree clean instead of overriding that.
- It has a `--force` option that ignores peer-dependency mismatches. Do not
  use it to get past a conflict; resolve the conflicting package.
- Third-party Angular libraries often ship their own `ng update` migrations.
  Update them with `ng update <package>` in the same stage.
- Optional migrations (standalone components, the new control flow) are
  separate schematics. They are refactors, not part of the upgrade.

## After the codemod

Whatever the tool, the stage is not done until every baseline check has been
recorded as passing in the ledger and `stage_ledger.py advance` accepts it.
