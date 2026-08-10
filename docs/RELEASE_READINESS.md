# Release Readiness Evidence

- Evidence date: 2026-08-10
- Candidate branch: `codex/beta-release-readiness`
- Validated implementation SHA: `2fe42f80fa55936852ef81c0e11e24e752c7ff63`
- Verified remote branch: `https://github.com/P0RTNOY/AI-Pictionary-Game/tree/codex/beta-release-readiness`
- Pull request: `https://github.com/P0RTNOY/AI-Pictionary-Game/pull/1`

This document separates measured local evidence from checks that still need credentials, hosted services, or devices. Passing evidence is tied to the immutable implementation SHA above and must not be copied to a source-changing commit without rerunning it.

## Passed automatically

Current working-tree checks executed on 2026-08-10:

- Final guess-judging plus Task 8 backend regressions — **24 passed in 12.56s**. Coverage includes non-blocking external scoring, immediate duplicate rejection, unrelated SQLite write progress while the judge is stalled, same-process HTTP/WebSocket responsiveness, owned finalization, stable recoverable judge/finalization errors, stale-claim recovery, exact notification-provider selection, Docker migration-context inclusion, authoritative clue counts, and submit/reveal linearizability.
- Full backend suite after the final integrated judging/mobile follow-up — **131 passed in 40.71s** on the immutable implementation SHA.
- Production-shaped migrated Uvicorn startup smoke — `/health` returned `status=ok` with `notification_provider=expo`, and unauthenticated `/debug/health/full` returned **404**; startup used `ENV=production`, `DEBUG=false`, `AUTO_CREATE_TABLES=false`, and no explicit notification-provider override.
- Two disposable SQLite migration paths passed at head `20260810_0006`: clean `upgrade head` / `downgrade 20260810_0005` / `upgrade head`, and previous-revision `upgrade 20260810_0005` / `upgrade head` / `downgrade 20260810_0005` / `upgrade head`. Downgrade restores any in-flight `judging` round to `ready`, removes `guess_claim_id`, and reinstates the previous active-round index predicate.
- Dockerfile source regression confirms the backend image includes `alembic.ini` and the full `alembic/` tree. An actual image build and one-shot in-container migration could not run because the local Docker daemon socket was unavailable; `docker version` failed to connect on the final retry.
- `npm ci` completed from the committed lockfile. A package-manager-only safe transitive refresh updated `brace-expansion`, `fast-uri`, `js-yaml`, and `shell-quote`; it made no `package.json`, override, major-SDK, or `lightningcss` change.
- Post-refresh `npm audit --omit=dev --json` reports **23 vulnerable package entries: 12 moderate and 11 high**, down from 27. The remaining advisory roots are `image-size`, `postcss`, and `uuid`; details and disposition are under Known non-blocking issues.
- `npx expo install --check` — dependencies are up to date.
- Task 3, Task 4, and Task 5 mobile checks, the expanded release URL/clue/judging/realtime-cursor lifecycle checks, and `npm run typecheck` passed with an explicit safe dummy staging HTTPS API URL. Realtime state is bounded, survives a background disable/enable for the same game/user identity, and resets on identity change.
- The final judging-navigation regression simulates `ready_to_guess` → `judging_started` → lost HTTP response → `round.scored`: the active Guess screen stays mounted and read-only during judging, then event/poll refresh reaches Result despite the advanced turn. It also proves old completed-game reopen behavior, judging interaction lockout, a 45-second submit deadline above the 35-second judge bound, and independent caller/background abort.
- Pinned Expo Doctor — **18/18 checks passed**.
- Public Expo config, production web export, and a live exported HTML-shell check passed with dotenv disabled and `EXPO_PUBLIC_API_URL=https://api.example.invalid`.
- Hosted GitHub Actions passed on the validated implementation SHA. Both push and pull-request runs completed the backend/migration job and the mobile static/lifecycle job successfully: [push run](https://github.com/P0RTNOY/AI-Pictionary-Game/actions/runs/31398256673) and [pull-request run](https://github.com/P0RTNOY/AI-Pictionary-Game/actions/runs/31398288955).

Earlier Task 7 evidence:

- Full backend suite launched with an inherited production-shaped environment and an unreachable PostgreSQL `DATABASE_URL` — **107 passed in 26.56s**. The harness overrode it before importing `app.db`; no external connection occurred.
- Focused test-database safety regression — **2 passed**. It verifies an exported sentinel SQLite application database remains byte-for-byte unchanged and a non-SQLite URL is never used.
- CI-shaped backend run with dotenv disabled and mock providers — **105 passed in 28.54s**. An earlier draft incorrectly set a global CI `DATABASE_URL`, which interfered with a test's disposable Alembic URL; the workflow now scopes that variable only to its migration step.
- A staged-tree snapshot materialized outside the repository (the same implementation source as the final follow-up commit): backend **107 passed in 82.27s** under the hostile inherited database environment; all three mobile security/lifecycle scripts, app-config guard, typecheck, pinned Expo Doctor **18/18**, and public Expo config passed.
- Fresh disposable SQLite: `alembic heads`, `upgrade head`, `current`, `downgrade -1`, `upgrade head`, `current` — passed; final revision was `20260810_0005 (head)`.
- `npm run test:task3-security` — passed.
- `npm run test:task4-lifecycle` — passed.
- `npm run test:task5-lifecycle` — passed.
- `node scripts/test-app-config.js` — passed the missing/malformed/non-HTTP(S)/loopback release URL guard.
- `npm run typecheck` — passed.
- `npm run doctor` (pinned `expo-doctor` 1.20.1) — **18/18 checks passed**.
- Development `npx expo config --type public --json` with dotenv disabled and an explicit loopback development URL — passed; output was written outside the repository.
- `.github/workflows/ci.yml` parsed as YAML and contains separate backend/mobile jobs. Hosted evidence for the final implementation SHA is recorded above.

Earlier exact-tree Task 6 evidence at commit `32186b8`:

- Full backend suite — **105 passed in 6.36s**; a separately materialized exact staged backend also passed all 105 tests.
- Mobile security/lifecycle scripts, typecheck, Expo Doctor, public config, and web export passed.
- Web export bundled 2,223 modules in the final Task 6 run.
- A migrated real Uvicorn HTTP/WebSocket smoke created two sessions, joined an invite, generated mock SVGs, kept the prompt hidden from the guesser, submitted a guess, polled events, issued a single-use WebSocket ticket, and replayed game-scoped events. Recorded result:

```json
{"event_count": 11, "http_lifecycle": "ok", "provider": "mock", "score": 100, "websocket_replay": "ok"}
```

Automated coverage includes authorization/IDOR boundaries, invite/round/guess atomic invariants, generation budgets, provider constructor/timeout/malformed/oversized/error paths, retry provenance, reset restrictions, device-token ownership/generations, notification bounds, WebSocket ticket consumption/replay, two-round lifecycle/statistics, cross-game isolation, deep-link parsing, stale-work retirement, and source-level secret/prompt logging guards.

Guess scoring now uses an explicit `judging` state and an opaque owned claim. The database claim commits before external judge I/O, the synchronous FastAPI route runs in the worker threadpool, and only the current claim may finalize or restore the round. The mobile UI represents this interval as **Scoring guess** rather than treating it as a generic wait.

## Passed locally / simulator

Passed locally:

- Backend startup and the two-player HTTP/WebSocket flow passed against fresh Alembic-head SQLite databases with mock AI/notifications.
- Uvicorn shut down normally after an idle WebSocket disconnect regression was fixed.
- Expo web export and a live web HTML-shell smoke passed during Task 5/6 validation.
- Xcode 26.6, an iOS 26.5 runtime, and a booted iPhone 17 Pro simulator were detected; the installed beta app connected to the task-owned Metro server and requested the current bundle.

No simulator gameplay pass is recorded. During the bounded Task 6 attempt, two unrelated Metro servers already occupied ports 8081/8082. The candidate server ran on 8083, but its bundle request stalled while Metro progressed to roughly 43%; the app remained at **Loading from Metro...**. The task-owned backend, Metro, and app process were stopped afterward without modifying the unrelated listeners.

## Requires external credentials

- Live OpenRouter SVG generation and judge scoring with a real key, including visual quality, provider usage, timeout/retry, and budget behavior.
- Real Expo push delivery/receipts with an Expo access token and configured iOS/Android push credentials.
- EAS development, preview, and production cloud builds, including environment selection and CNG asset verification.
- Deployment-platform staging check with real secret storage, TLS API URL, explicit CORS origins, and debug routes unavailable.
- PostgreSQL Alembic upgrade/downgrade and concurrency behavior on the actual deployment major/version. SQLite migration and invariant paths passed; PostgreSQL was not executed.
- A real OpenAI-compatible local model quality run if `AI_PROVIDER=local` will be offered.

## Requires physical-device QA

- Fresh install and two-player/two-device lifecycle on physical iOS.
- Physical Android lifecycle, or an explicit decision that Android is outside this beta candidate.
- Push permission, token rotation/unregister, background delivery, notification tap, and cross-game authorization.
- Cold/warm custom-scheme links and any production universal/app links actually distributed.
- Suspend/resume, network loss, WebSocket flapping, polling fallback, and rapid game switching on real networks.
- VoiceOver/TalkBack, dynamic type, color-independent selected state, touch targets, and loading/disabled announcements.
- Final icon, splash, package/bundle identifier, and API/environment display in installed EAS artifacts.

## Known non-blocking issues

- The post-refresh npm audit still exits nonzero with **23 entries (12 moderate, 11 high)** rooted in `image-size`, `postcss`, and `uuid`. In this SDK 54 graph they are reached through Metro/Expo configuration or Xcode project tooling, not the shipped application runtime or user-controlled backend request path. npm offers only breaking Expo/React Native changes for these roots. They are therefore upstream-blocked build-tool risk for this candidate, not silently ignored; reassess on the next Expo-supported SDK update and do not use untrusted image/CSS/project inputs in build automation.

- The local simulator tooling attempt did not finish a current JavaScript bundle. Automated lifecycle checks and web export pass, but this is not simulator UI evidence.
- Local SQLite and the in-process invite limiter are appropriate only for the current single-service development/beta shape. Multi-instance deployment needs PostgreSQL and a shared rate limiter.
- The repository previously reported missing local Git objects during an exact-index archive. On 2026-08-10, the previously named objects were readable and `git fsck --connectivity-only --no-dangling` exited cleanly. Final publication should still verify the pushed remote branch rather than assuming the earlier local issue is permanently resolved.
- `npm ci` prints deprecation warnings in transitive Expo/Metro tooling. They do not fail install, typecheck, Doctor, config, or export.
- Docker runtime evidence is incomplete on this machine because no Docker daemon was available. The image-context regression passes, but the release image must still be built and run with `alembic upgrade head` against a disposable database in CI or the deployment platform.
- Production universal links/app links require domain association files and native configuration; only the custom development scheme and pure parser behavior are currently implemented/covered.

## Release blockers

- The production backend image build plus in-container `alembic upgrade head` remains a release check until executed on a Docker-capable CI runner or deployment platform.
- External beta distribution should wait for at least one complete physical iOS two-player pass. Android must either pass or be explicitly removed from scope.
- If the candidate advertises real AI or push, the corresponding live OpenRouter and Expo push checks above are blockers until recorded.
- A PostgreSQL-backed staging deployment is blocked until the migration chain and core lifecycle are executed against that target database.
- Production universal/app links are blocked until their domain association and native handoff are configured and tested; use only the documented development custom scheme until then.

## Publication follow-up checklist

1. Reverify the remote branch head and pull-request checks after the documentation-only publication metadata commit.
2. Move completed external/device items into the passed sections with build/device/provider evidence.
3. Leave any unmet item in **Release blockers** with an explicit scope decision.
