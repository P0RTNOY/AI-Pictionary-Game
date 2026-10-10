# Task 8 release-fix implementation report

Status: implementation complete on `codex/beta-release-readiness`; no push performed.

Final implementation HEAD inspected before the final evidence-only commit: `ba4ac44`
Final evidence commit before the integrated judging/mobile follow-up: `58411ca`
Final integrated judging/mobile commit: `2fe42f8`

## Focused commits

- `6440921` — `fix: make release state server authoritative`
- `1e4e63b` — `fix: persist authoritative clue reveals`
- `284cd15` — `chore: refresh safe mobile transitive locks`
- `4db9332` — `fix: reject wildcard CORS outside local debug`
- `bdee0f9` — `docs: record final beta release evidence`
- `f69dceb` — `fix: retire clue work when rounds change`
- `aebf81e` — `docs: align release evidence with final source`
- `4b3f651` — `fix: include migrations in backend image`
- `38d21c9` — `fix: fail closed on notification providers`
- `f3c9b4e` — `fix: preserve realtime cursors across backgrounding`
- `222887c` — `fix: score guesses outside database transactions`
- `ba4ac44` — `fix: represent in-progress guess scoring`
- `58411ca` — `docs: record final release review evidence`
- `2fe42f8` — `fix: preserve mobile guess judging flow`

## Changes

- Backend configuration now defaults missing `ENV` to production, permits debug/automatic schema compatibility only for explicit local/test environments, removes wildcard CORS outside local debug, and gives the Docker image production-shaped defaults.
- `AUTO_CREATE_TABLES=false` now prevents both ORM table creation and SQLite light-migration mutation. Alembic remains the deployable schema path.
- Every application SQLite connection enables `PRAGMA foreign_keys=ON`. Regression coverage checks `foreign_key_check` and proves a stale generation cannot repopulate reset data with orphan rows.
- Alembic revision `20260810_0004` uses its historical local token-limit constant (`3`) instead of importing mutable runtime configuration.
- Added authenticated guesser-only `POST /rounds/{round_id}/reveal-clue`. The conditional update persists and bounds reveals by completed SVG rows. Guess submission atomically transitions the round while returning the stored reveal count, ignores the legacy client clue count, and scores/persists the authoritative count. Concurrent reveal and submit/reveal races are covered.
- Mobile now persists a reveal before displaying it, restores/clamps the visible count from round state, and generation-gates/aborts reveal work alongside guess work. Duplicate reveal/submit paths disable each other.
- Native API URL safety now runs at Expo config time for staging/production environments and preview/production build profiles, plus at runtime whenever `__DEV__` is false. Omitted release environment labels cannot silently select loopback. CI config/export uses an explicit safe dummy staging HTTPS URL.
- The lockfile-only npm refresh updated vulnerable compatible transitive releases for `brace-expansion`, `fast-uri`, `js-yaml`, and `shell-quote`. It changed neither `package.json` nor npm overrides/major SDK versions; `lightningcss` remained `1.33.0`.
- README, beta QA, release-candidate QA, CI, and release-readiness evidence now describe authoritative clues, fail-closed deployment/runtime configuration, exact checks, and the dependency-audit disposition. Final SHA/remote/PR placeholders remain for the root publication step.
- The backend image now includes the complete Alembic context. Notification configuration accepts exactly `mock` or `expo`, defaults to mock only for local/dev/test, defaults to Expo elsewhere, and exposes the selected provider in `/health`.
- Guess judging now uses an owned `judging` claim committed before external provider I/O. Duplicate work is rejected, stale claims and judge/finalization failures are recoverable, only the owner can finalize, and the sync route runs in FastAPI's worker threadpool.
- Mobile renders the judging interval as **Scoring guess** and preserves a bounded realtime cursor across background disable/enable for the same game/user identity.
- The final integrated lifecycle fix keeps the guesser's same-round Guess screen mounted through `judging_started`, disables guess/reveal interaction while judging, and routes a later scored refresh to Result even when the HTTP response is lost. An observed-round navigation context is cleared on Home, game open, and Next so reopening old completed games retains normal routing.
- Guess submission uses a composed 45-second endpoint deadline above the backend judge's 35-second provider timeout while retaining immediate caller/background abort.

## Files changed by this fix batch

- `.github/workflows/ci.yml`
- `README.md`
- `backend/.env.example`
- `backend/Dockerfile`
- `backend/alembic/versions/20260810_0004_device_token_ownership.py`
- `backend/alembic/versions/20260810_0006_guess_judging_claims.py`
- `backend/app/config.py`
- `backend/app/db.py`
- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/notifications.py`
- `backend/app/routes/rounds.py`
- `backend/app/services.py`
- `backend/tests/test_game_flow.py`
- `backend/tests/test_guess_judging.py`
- `backend/tests/test_task8_release_fixes.py`
- `docs/BETA_TESTING.md`
- `docs/RELEASE_CANDIDATE_QA.md`
- `docs/RELEASE_READINESS.md`
- `mobile/app.config.js`
- `mobile/package-lock.json`
- `mobile/scripts/test-app-config.js`
- `mobile/scripts/test-task5-lifecycle.js`
- `mobile/src/api/rounds.ts`
- `mobile/src/apiUrlSafety.ts`
- `mobile/src/clueRevealState.ts`
- `mobile/src/config.ts`
- `mobile/src/realtimeCursor.ts`
- `mobile/src/requestTimeouts.ts`
- `mobile/src/roundLifecycle.ts`
- `mobile/src/hooks/useGameEvents.ts`
- `mobile/src/screens/GuessScreen.tsx`

## Validation executed

- TDD RED observed for missing/unknown environment defaults, SQLite foreign-key enforcement, absent reveal service, concurrent reveal behavior, missing mobile clue/runtime-safety modules, omitted-env EAS release guard, and explicit wildcard CORS under unknown `ENV`.
- Focused backend Task 8 tests: `9 passed in 2.35s`.
- Full backend suite after source fixes: `116 passed in 10.84s`.
- Final exact-HEAD backend suite under production-shaped exported flags: `116 passed in 18.64s`.
- Final guess-judging plus Task 8 focused suite: `24 passed in 12.56s`.
- Final full backend suite: `131 passed in 49.01s`.
- Final full backend suite after the integrated mobile follow-up: `131 passed in 33.17s`.
- Production-shaped missing-env subprocess/API regression: debug route `404`; blank SQLite schema remained blank.
- Actual migrated Uvicorn startup smoke: `/health` passed; `/debug/health/full` returned `404` under `ENV=production`, `DEBUG=false`, `AUTO_CREATE_TABLES=false`.
- Alembic head: `20260810_0006`.
- Clean upgrade/downgrade/re-upgrade and `20260810_0005` to head/downgrade/re-upgrade passed on disposable SQLite databases; downgrade restores in-flight judging rounds before removing the claim column.
- Fresh SQLite: upgrade head, current, downgrade to `20260810_0004`, re-upgrade head — passed.
- Previous-revision SQLite: upgrade `20260810_0003`, upgrade `20260810_0004`, downgrade `20260810_0003`, upgrade head — passed.
- `npm ci` from the refreshed lockfile — passed (`733` packages installed, `734` audited).
- `npm run test:task3-security` — passed.
- `npm run test:task4-lifecycle` — passed.
- `npm run test:task5-lifecycle` — passed, including authoritative clue state and runtime loopback cases.
- `node scripts/test-app-config.js` — passed, including omitted app env with `EAS_BUILD_PROFILE=production`.
- `npm run typecheck` — passed.
- `npx expo install --check` — dependencies up to date.
- Pinned `npm run doctor` — `18/18` checks passed.
- Public Expo config and production web export with dotenv disabled and `EXPO_PUBLIC_API_URL=https://api.example.invalid` — passed; exported HTML contains the application root. An earlier live HTTP shell fetch also passed.
- Final web export HTTP smoke fetched the generated HTML and JavaScript bundle successfully.
- After the judging/mobile follow-up, Task 3/4/5 checks, app-config guard, typecheck, dependency consistency, Expo Doctor `18/18`, public config, production web export, and live exported HTML/JavaScript fetch all passed again.
- `npm audit --omit=dev --json` — expected nonzero status with `23` entries (`12 moderate`, `11 high`, `0 critical`), reduced from `27`; remaining advisory roots are `image-size`, `postcss`, and `uuid`.
- CI workflow YAML parsed and uses the safe dummy staging HTTPS config for config/export validation.
- `git diff --check cd63f3f..HEAD`, clean status, ancestry check, `git fsck --connectivity-only --no-dangling`, tracked generated-file inspection, `.env` tracking guard, and focused secret-pattern scan — passed. Base `cd63f3f` remains an ancestor; `91` files differ across the whole release branch.

## Remaining risks and unavailable evidence

- PostgreSQL was not available. PostgreSQL Alembic and real transaction/concurrency behavior remain a staging blocker; SQLite migration/concurrency/FK paths passed.
- Docker CLI was present but the daemon socket was unavailable on the final retry. The Dockerfile regression proves the migration context is copied, but an actual image build and in-container `alembic upgrade head` remain required on a Docker-capable CI/deployment runner.
- No live OpenRouter key, Expo push credentials, or EAS cloud build credentials were used. Those provider/delivery/build checks remain external.
- No complete current physical-device or simulator two-player gameplay pass was performed for this fix batch. Earlier simulator startup evidence remains incomplete; physical iOS is a release blocker and Android needs a pass or explicit scope removal.
- npm audit still reports 23 aggregate entries rooted in `image-size`, `postcss`, and `uuid`. In the pinned SDK 54 tree they are Metro/Expo configuration or Xcode build-tool paths, not shipped application runtime paths. npm proposes only incompatible Expo/React Native changes. This is documented upstream-blocked build-tool risk, not hidden; do not use `npm audit fix --force`.
- Hosted CI, remote branch verification, final candidate SHA insertion, push, and pull request creation are intentionally left to the root publication step.
