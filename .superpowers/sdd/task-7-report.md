# Task 7 report — CI, documentation reconciliation, and release evidence

## Outcome

Completed and committed as `c132064 docs: add beta release CI and evidence` on `codex/beta-release-readiness`.

The focused commit contains only CI, documentation, and environment examples. Pre-existing unstaged changes in `backend/app/ai.py` and `backend/app/services.py` remain untouched and unstaged.

## CI

Added `.github/workflows/ci.yml` with read-only repository permissions, cancellation of superseded runs, timeouts, and two jobs:

- Backend: Python 3.12, pip cache, `requirements.txt`, full pytest suite, and a fresh SQLite Alembic `heads -> upgrade head -> current -> downgrade -1 -> upgrade head -> current` round trip.
- Mobile: Node 20, npm cache, `npm ci`, Task 3 security/Task 4 lifecycle/Task 5 lifecycle checks, release API URL guard, TypeScript, Expo Doctor, and public Expo config.

Both jobs use mock providers and no secrets/live services. Python dotenv loading is disabled in CI. The migration database URL and `AUTO_CREATE_TABLES=false` are scoped only to the migration step.

The first CI draft set `DATABASE_URL` globally. A local CI-shaped run exposed that this overrides a migration test's own disposable Alembic URL, causing `table users already exists` (1 failed, 104 passed). Scoping the URL to the migration step fixed the workflow shape; the corrected dotenv-disabled run passed all 105 tests.

## Documentation and configuration examples

- Rewrote README onboarding, provider, migration, session, reset, mobile/EAS, API authorization, realtime, notification, validation, and deployment guidance against current source.
- Rebuilt `docs/BETA_TESTING.md` around safe local reset, one-time session re-onboarding, capability-safe invite/deep-link testing, provider/judge/provenance row distinctions, two-player lifecycle, push, and stale-work checks.
- Rebuilt `docs/RELEASE_CANDIDATE_QA.md` as an immutable-candidate checklist with exact automated preflight, target migration, EAS, session/auth, two-device, provider, push, link, accessibility, reset, and exit criteria.
- Added `docs/RELEASE_READINESS.md` with the required passed/external/physical/known-issue/blocker sections, Task 6 real-server and bounded simulator evidence, and candidate SHA/remote/PR placeholders for Task 8.
- Extended backend and mobile environment examples with every current operational bound/timeout plus `LOG_LEVEL` and `APP_PUBLIC_URL`; no credential value was copied.
- Removed stale instructions that exposed prompt text or relied on `Submitting prompt`, backend prompt logs, bearer/user-ID WebSocket URLs, capability-in-path production invites, DEBUG-only reset assumptions, raw SQLite file deletion, or implicit OpenRouter switching.

## Validation

Backend:

- Normal working tree: `backend/.venv/bin/python -m pytest -q` — 105 passed in 30.76s.
- Corrected CI-shaped run with `PYTHON_DOTENV_DISABLED=1`, mock providers, and no global database URL — 105 passed in 28.54s.
- Fresh SQLite Alembic heads/upgrade/current/downgrade/upgrade/current — passed, ending at `20260810_0005 (head)`.
- `python -m pip check` — no broken requirements.

Mobile:

- `npm ci` — installed successfully.
- Task 3 security, Task 4 lifecycle, Task 5 lifecycle — passed.
- `node scripts/test-app-config.js` — passed.
- `npm run typecheck` — passed.
- Expo Doctor, including dotenv-disabled CI shape — 18/18 passed.
- Public Expo config with explicit development values and dotenv disabled — passed.
- `npm ls --depth=0` — passed and matched the SDK 54 package graph.

Exact staged snapshot materialized with `git write-tree`/`git archive` outside the repository:

- backend — 105 passed in 11.56s;
- all mobile security/lifecycle scripts, config guard, typecheck, Expo Doctor 18/18, and public Expo config — passed.

Documentation/repository checks:

- Workflow parsed as YAML with backend/mobile jobs.
- All local Markdown links and documented repository paths resolve.
- Searches found no stale `Submitting prompt`, prompt-log, old WebSocket auth, old invite route, raw reset, absolute workstation path, or credential/token patterns in Task 7 files.
- `git diff --cached --check` and staged secret-pattern scan passed.
- `git fsck --connectivity-only --no-dangling` passed; `git archive` of the staged tree also succeeded, so the earlier missing-object condition was not reproduced.

## Remaining risks and blockers

- No hosted GitHub Actions run exists until the branch is pushed.
- `npm ci` and `npm audit --omit=dev` report 27 vulnerable package entries (12 moderate, 15 high) in the Expo/React Native/Metro graph. Individual entries can aggregate multiple advisories. Suggested fixes include incompatible SDK majors. This is documented as a release blocker for focused dependency/security triage; no forced audit fix was applied.
- PostgreSQL, OpenRouter, Expo push, EAS cloud builds, production links, physical-device two-player/accessibility/network QA remain unexecuted and explicitly separated in release readiness.
- The prior bounded simulator attempt reached Metro but not current-JavaScript startup; it is documented as a limitation, not a pass.
- Task 8 must update final SHA/remote/PR/CI fields and rerun exact final validation after any source changes.

## Review follow-up: destructive test safety and reproducible Doctor

Completed and committed separately as `32d462e fix: make release validation deterministic and safe`; the original Task 7 commit was not amended and nothing was pushed.

### Root cause and TDD evidence

`backend/tests/conftest.py` imported `app.db` before setting a test database. SQLAlchemy therefore captured any inherited application `DATABASE_URL`, and the autouse fixture immediately ran `drop_all`/`create_all` against that engine.

RED 1 added a subprocess regression with a sentinel SQLite application database and an unreachable PostgreSQL-shaped URL. Both cases failed because the harness had no dedicated test database constants/override:

```text
2 failed in 6.31s
ImportError: cannot import name 'TEST_DATABASE_DIRECTORY' from 'conftest'
```

GREEN 1 made conftest create an unmistakable `ai-pictionary-pytest-only-*` system-temp directory, override all database/test/provider/dotenv settings before importing `app.db`, and remove `DATABASE_URL` afterward so Alembic tests retain their per-test URLs:

```text
2 passed in 1.11s
```

RED 2 required a fail-closed invariant immediately around every destructive fixture operation:

```text
2 failed in 3.21s
ImportError: cannot import name 'assert_dedicated_test_database' from 'conftest'
```

GREEN 2 added the guard, which refuses destructive setup unless the bound engine is SQLite at the exact dedicated test path:

```text
2 passed in 2.20s
```

The regression proves the sentinel database remains byte-for-byte unchanged with its table/value/user-version intact, the remote-shaped URL is never connected, the test engine is under the dedicated normal (non-symlink) system-temp directory, dotenv is disabled, and migration configuration is not shadowed.

### Other review fixes

- `.gitignore` now ignores `.env.*` while explicitly retaining `.env.example` files.
- Pinned the same official registry version previously resolved by unpinned npx, `expo-doctor@1.20.1`, as an exact dev dependency. Added `npm run doctor`, pinned CI Node to the package's supported minimum `20.19.4`, and updated commands/docs. This is a low-risk dev-tool-only pin with no runtime bundle dependency.
- Corrected release evidence from “27 advisories” to “27 vulnerable package entries”; npm's entries may each aggregate multiple advisories.
- Documented safe plain pytest behavior and the fixture-owned temporary database in README and release-candidate QA.

### Follow-up validation

- Full backend suite with inherited production/openrouter/expo settings and an unreachable PostgreSQL URL: 107 passed in 26.56s; no remote connection.
- Focused safety probe: 2 passed.
- Migration-focused tests: 2 passed; fresh Alembic head/current/downgrade/upgrade/current ended at `20260810_0005 (head)`.
- `npm ci`: passed with the pinned lockfile.
- Task 3/4/5 mobile scripts, config guard, typecheck, public Expo config: passed.
- `npm run doctor`: 18/18 passed, including dotenv-disabled CI shape; `expo-doctor --version` returned 1.20.1.
- Exact staged snapshot: backend 107 passed in 82.27s under the hostile inherited DB environment; complete mobile validation passed, including pinned Doctor 18/18.
- Workflow YAML, Markdown links, ignore behavior, package metadata, stale-command search, `git diff --cached --check`, and secret-pattern scan passed.
- `npm audit --omit=dev` still reports exactly 27 vulnerable package entries (12 moderate, 15 high, 0 critical); no force fix was applied.
