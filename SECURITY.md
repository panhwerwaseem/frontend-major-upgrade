# Security

An agent skill is instructions and code that your coding agent will follow and run. Review a skill before installing it, the same way you would review any dependency.

## What this skill does on your machine

| | |
|---|---|
| Reads | `package.json`, JavaScript and TypeScript sources and `tsconfig*.json` in the project folder you pass; `node_modules/<package>/package.json` for installed versions and peer ranges, when present; its own ledger file |
| Writes | `ledger.json` and one log per check inside `.frontend-upgrade/`, or in the folder of the `--ledger` path. `upgrade_scan.py` and `upgrade_rules.py` write nothing |
| Executes | Only `stage_ledger.py verify`, which runs the check command you pass after `--`, directly, without a shell, in the `--project` folder. No script runs npm, npx, a package install or a codemod |
| Network | None. The bundled scripts import no network modules. `tools/validate.py` checks this in CI |
| Dependencies | Python standard library only |
| Pre-approved tools | None. `SKILL.md` has no `allowed-tools` entry, so your agent's normal permission prompts apply |
| Hooks, MCP servers, background processes | None |

The skill instructs the agent to change dependency versions, run the framework's official codemods, and edit source files. Those actions are taken by the agent, not by the bundled scripts, and go through your agent's normal review and permission flow.

Two cautions specific to this skill:

- **Codemods and installs run third-party code.** `npx <codemod>`, `ng update` and a package install download and execute packages from the npm registry, including install scripts. Check the package name against the framework's upgrade guide before approving the command, and run upgrades on a branch with a clean working tree.
- **The ledger is a record, not a lock.** It is a JSON file in your project. It stops an agent that follows the protocol from skipping a stage, and it shows a reviewer what was run. It does not stop someone from editing the file or the code by hand. Review the ledger's commands and logs, not only its "passed" marks; a check whose command differs from the baseline is flagged for that reason.

## Reporting a vulnerability

Please report security problems privately through the repository's **Security** tab ("Report a vulnerability"). If that option is not available, open an issue that says a private channel is needed, without including exploit details.

## Verifying what you install

- Install from a tagged release and read the diff between tags before updating.
- The whole skill is the `skills/frontend-major-upgrade/` folder: one Markdown protocol, three Python scripts, three reference files, and eval fixtures.
