# Changelog

All notable changes to this skill are recorded here. Versions follow [Semantic Versioning](https://semver.org).

## 0.1.0 - 2026-11-06

### Added

- `SKILL.md` with the upgrade protocol: seven hard rules and a five-step workflow.
- `scripts/upgrade_scan.py`: framework and version detection, the staged path, family and peer-range checks, and pattern findings with file and line.
- `scripts/upgrade_rules.py`: the rule table as data, with a self-check that tests every pattern against its examples.
- `scripts/stage_ledger.py`: baseline and per-stage verification records, with refusal to advance past a failing or unverified stage.
- References for the staged method, breaking changes by framework and major, and codemod usage.
- Four fixtures (React 16, Next.js 13, Angular 15, and a clean React 18 app) with eval cases, and trigger queries.
- Unit tests, a format validator, and a CI workflow.
