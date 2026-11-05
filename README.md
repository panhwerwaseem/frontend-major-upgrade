# frontend-major-upgrade

**An agent skill that runs a React, Next.js or Angular major upgrade one major at a time, codemods first, with a recorded build and test result at every stage.**

Left alone, a coding agent asked to "upgrade to React 19" tends to edit `package.json` straight to the target, fix whatever the compiler complains about by hand, refactor nearby code on the way, and report success after a build that half works. This skill replaces that with a protocol and three scripts: no version change before a green baseline is recorded, one major per stage, the official codemod before any hand edit, the framework's family of packages moved together, and no next stage until the current one has passed the same checks as the baseline.

Works with Claude Code, and with any agent that reads the open [Agent Skills](https://agentskills.io) format (Codex, Cursor, GitHub Copilot, Gemini CLI and others).

## What it looks like

Planning an Angular 15 to 17 upgrade. The scan reads `package.json` and the sources; it runs nothing:

```console
$ python3 scripts/upgrade_scan.py evals/files/angular-15-material --to 17
project: evals/files/angular-15-material
framework: angular   current: @angular/core 15   target: 17
version evidence: package.json dependencies.@angular/core "^15.2.0"
note: Version read from the declared range, not from an installed package.
path: 15 -> 16 -> 17 (2 stages, one major each)

Before stage 1
  [break] family-mismatch: @angular/cdk is on major 14 but @angular/material is on 15
      package.json dependencies.@angular/cdk  "^14.2.0" (@angular/material "^15.2.0")
      fix: Align it with @angular/material inside the current major before the first stage: @angular/material peer-depends on the matching @angular/cdk.
  [break] family-mismatch: @angular/router is on major 14 but @angular/core is on 15
      package.json dependencies.@angular/router  "^14.2.0" (@angular/core "^15.2.0")
      fix: Align it with @angular/core inside the current major before the first stage: Angular framework packages are released together and peer-depend on the same @angular/core.

Stage 1: @angular/core 15 -> 16 (with @angular/material 15 -> 16)
  move together: @angular/animations, @angular/cdk, @angular/cli, @angular/common, @angular/compiler, @angular/compiler-cli, @angular/core, @angular/forms, @angular/material, @angular/platform-browser, @angular/platform-browser-dynamic, @angular/router
  guide: https://angular.dev/update-guide
  codemod: ng update @angular/core@16 @angular/cli@16   (runs that major's migrations)
  codemod: ng update @angular/material@16   (only when Angular Material is installed)
  note: The compatibility compiler (ngcc) is removed, so libraries published only in View Engine format stop working.
  note: Node.js, TypeScript and RxJS ranges change with the Angular major: check https://angular.dev/reference/versions for this stage.
  [break] angular-entry-components: entryComponents
      src/app/app.module.ts:20  entryComponents: [ConfirmDialogComponent],
      fix: Delete the entryComponents array. Ivy has not needed it since Angular 9.

Stage 2: @angular/core 16 -> 17 (with @angular/material 16 -> 17)
  move together: @angular/animations, @angular/cdk, @angular/cli, @angular/common, @angular/compiler, @angular/compiler-cli, @angular/core, @angular/forms, @angular/material, @angular/platform-browser, @angular/platform-browser-dynamic, @angular/router
  guide: https://angular.dev/update-guide
  codemod: ng update @angular/core@17 @angular/cli@17   (runs that major's migrations)
  codemod: ng update @angular/material@17   (only when Angular Material is installed)
  note: Angular Material 17 removes the legacy (pre-MDC) components.
  note: Node.js, TypeScript and RxJS ranges change with the Angular major: check https://angular.dev/reference/versions for this stage.
  [break] angular-material-legacy: @angular/material/legacy-* imports
      src/app/app.component.ts:2  import { MatLegacyDialog as MatDialog } from '@angular/material/legacy-dialog';
      src/app/app.module.ts:4  import { MatLegacyButtonModule } from '@angular/material/legacy-button';
      src/app/app.module.ts:5  import { MatLegacyDialogModule } from '@angular/material/legacy-dialog';
      src/app/confirm-dialog.component.ts:2  import { MAT_LEGACY_DIALOG_DATA as MAT_DIALOG_DATA } from '@angular/material/legacy-dialog';
      fix: Move to the MDC-based components (the import path without legacy-). The Angular Material 15 migration guide covers the schematic and the style changes.

peer ranges: not checked (no node_modules folder, so peer ranges of installed dependencies were not checked)
summary: 7 break, 0 review, 0 deprecated; 5 file(s) scanned
A scan with no findings is not proof of a safe upgrade. Verify every stage with stage_ledger.py.
```

A scan with no findings says so, and says what that is worth:

```console
$ python3 scripts/upgrade_scan.py evals/files/react-18-modern --to 19
project: evals/files/react-18-modern
framework: react   current: react 18   target: 19
version evidence: package.json dependencies.react "^18.3.1"
note: Version read from the declared range, not from an installed package.
path: 18 -> 19 (1 stage, one major each)

Stage 1: react 18 -> 19
  move together: @types/react, @types/react-dom, react, react-dom
  guide: https://react.dev/blog/2024/04/25/react-19-upgrade-guide
  codemod: npx codemod@latest react/19/migration-recipe   (recipe named in the React 19 upgrade guide)
  codemod: npx types-react-codemod@latest preset-19 <path>   (TypeScript projects)
  note: Move to the latest react 18.3 first: it warns about the APIs that 19 removes.
  note: 19 requires the new JSX transform.
  note: propTypes checks are ignored in 19; read the guide for the other behaviour changes.
  no findings (the rule table has 11 rule(s) for this stage)

peer ranges: not checked (no node_modules folder, so peer ranges of installed dependencies were not checked)
summary: 0 break, 0 review, 0 deprecated; 6 file(s) scanned
A scan with no findings is not proof of a safe upgrade. Verify every stage with stage_ledger.py.
```

The ledger refuses to verify a stage that has not been installed, and refuses to move past a stage with a failing check. (The fixtures ship without installed dependencies, so this transcript uses two stand-in scripts, `ci/build.py` and `ci/test.py`, where a real project would pass `npm run build` and `npm test`.)

```console
$ python3 scripts/stage_ledger.py verify --check test -- python3 ci/test.py
REFUSED: stage '16 -> 17' expects react 17, but package.json dependencies.react "^16.14.0". Do this stage's upgrade and install first.
Nothing was run or recorded.

$ python3 scripts/stage_ledger.py verify --check test -- python3 ci/test.py
16 -> 17: test FAIL (exit 1, attempt 1, 0.0s)
    FAIL src/__tests__/SearchBox.test.js
      x submits the typed text
    Tests: 1 failed, 1 passed, 2 total
log: .frontend-upgrade/16-to-17-test.log

$ python3 scripts/stage_ledger.py advance
REFUSED to advance past '16 -> 17':
  - check 'test' last result is fail

$ python3 scripts/stage_ledger.py status
ledger: .frontend-upgrade/ledger.json
package: react   path: 16 -> 19   current stage: 16 -> 17
  baseline   passed   build pass, test pass
  16 -> 17   open     build pass, test FAIL
  17 -> 18   pending  -
  18 -> 19   pending  -
A check is failing on the current stage. Fix it and re-run verify; advance is refused until every check passes.
```

## Install

Pick one route. Installing through more than one gives you the skill twice.

**Claude Code (plugin)**

```
/plugin install frontend-major-upgrade --marketplace panhwerwaseem/frontend-major-upgrade
```

On Claude Code versions before 2.1.275, use two steps:

```
/plugin marketplace add panhwerwaseem/frontend-major-upgrade
/plugin install frontend-major-upgrade@panhwerwaseem-frontend-major-upgrade
```

**Any agent (skills CLI)**

```bash
npx skills add panhwerwaseem/frontend-major-upgrade
```

**Manual**

Copy the `skills/frontend-major-upgrade` folder into `.claude/skills/` (Claude Code) or `.agents/skills/` (cross-agent) in your project, or into the same folder under your home directory.

To pin a release, add the tag: `/plugin marketplace add panhwerwaseem/frontend-major-upgrade#v0.1.0` or `npx skills add panhwerwaseem/frontend-major-upgrade@v0.1.0`. Third-party plugins do not update automatically; run `claude plugin update frontend-major-upgrade@panhwerwaseem-frontend-major-upgrade` to update.

## Use

Describe the upgrade and the skill loads on its own:

> We're on Next 13 with React 18. Get us to Next 15. CI runs `npm run build` and `npm test`.

In Claude Code you can also call it directly with `/frontend-major-upgrade`.

## What is in the skill

| File | Purpose |
|---|---|
| `SKILL.md` | The protocol: seven hard rules and a five-step workflow from baseline to report |
| `scripts/upgrade_scan.py` | Reads `package.json` for the framework and version, prints the path one major at a time, the packages that move together, the official guide and codemod entry point per stage, and findings with file and line. With `node_modules` present it also checks the peer ranges of installed direct dependencies |
| `scripts/upgrade_rules.py` | The rule table as plain data: for each rule the governing package, the major that removed the API, the pattern, and examples it must and must not match. `--check` tests every pattern against its examples |
| `scripts/stage_ledger.py` | Records a baseline and each stage with named checks. Runs the check command you pass, stores exit code and log, and refuses to advance past a stage that failed, was not installed, or dropped a baseline check |
| `references/staged-method.md` | How to run one stage, what counts as verification, and what is not part of an upgrade |
| `references/breaking-changes.md` | The rules by framework and major, and the behaviour changes no pattern can find |
| `references/codemods.md` | The official migration tools for React, Next.js and Angular, and how to use them safely |
| `evals/` | Four small apps (React 16, Next.js 13, Angular 15, and a clean React 18 app) with eval cases, plus trigger queries |

### What the scan covers, and what it does not

The rule table is short on purpose. It holds only removals stated in the official upgrade guides: the React 19 removals, a set of Next.js changes from 13 to 16, and four Angular rules. Angular's own `ng update` migrations do most of that framework's source changes, so the scan's main job there is the path, the family check and the peer check.

The scan matches regular expressions on comment-stripped source. It does not follow import aliases, does not parse templates, and cannot see behaviour changes such as new caching defaults. A stage with no rules prints "the rule table has 0 rule(s) for this stage: read the guide". The scan never looks up the latest version; you pass the target with `--to`.

## Requirements

- Python 3.9 or later
- No packages to install and no network access for the scripts
- The upgrade itself uses your project's package manager and the framework's codemods. Your agent runs those, with your approval; the scripts do not.

## What it reads, writes and contacts

- **Reads:** `package.json`, JavaScript and TypeScript sources, and `tsconfig*.json` in the project you point it at; `node_modules/<package>/package.json` for installed versions and peer ranges when that folder exists.
- **Writes:** the ledger file and check logs inside `.frontend-upgrade/` (or next to the path passed to `--ledger`). `upgrade_scan.py` and `upgrade_rules.py` write nothing.
- **Runs:** `stage_ledger.py verify` runs the check command you pass after `--`, directly, without a shell. The scripts never run npm, npx, a package install or a codemod.
- **Contacts:** nothing. The scripts contain no network code; CI enforces this.
- **Permissions:** the skill pre-approves no tools. Your agent asks before running commands, as usual.

See [SECURITY.md](SECURITY.md).

## Testing status

- The scripts have unit tests that run in CI on Python 3.9 and 3.12, together with a validator for the skill format and plugin manifests. The tests run each script against every fixture and check that each planted finding is reported and that the clean fixture reports none.
- The eval cases in `skills/frontend-major-upgrade/evals/` are in the [skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator) format. A with-skill versus without-skill score has not been published yet; results are welcome as an issue or pull request.
- The fixtures contain no `node_modules` and no lockfile. The scripts have not been run by this repository's tests against a full installed application.

## Development

```bash
python3 tools/validate.py              # skill format, manifests, no-network check
python3 -m unittest discover -s tests  # script unit tests
python3 skills/frontend-major-upgrade/scripts/upgrade_rules.py --check  # every rule against its examples
```

To add a rule, add one entry to `RULES` in `scripts/upgrade_rules.py` with the major that removed the API, a link to where the official guide says so in your pull request, and at least one `match` and one `no_match` example.

## License

[MIT](LICENSE)
