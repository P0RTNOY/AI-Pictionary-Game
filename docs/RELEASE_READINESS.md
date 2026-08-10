# Release Readiness Evidence

- Evidence date: 2026-08-10
- Candidate branch: `codex/beta-release-readiness`
- Implementation SHA inspected before documentation/CI commit: `32186b83c4192cc790387befa4f21a50d6097ef1`
- Final candidate SHA: `<update after Task 8 final validation>`
- Verified remote branch: `<update after push>`
- Pull request: `<update with URL, or record unavailable>`

This document separates measured local evidence from checks that still need credentials, hosted services, or devices. Placeholders must be updated against one immutable final candidate; passing evidence must not be copied from a different commit after source changes.

## Passed automatically

Current working-tree checks executed on 2026-08-10:

- `backend/.venv/bin/python -m pytest -q` — **105 passed in 30.76s**.
- CI-shaped backend run with dotenv disabled and mock providers — **105 passed in 28.54s**. An earlier draft incorrectly set a global CI `DATABASE_URL`, which interfered with a test's disposable Alembic URL; the workflow now scopes that variable only to its migration step.
- A staged-tree snapshot materialized outside the repository (the same implementation source as the final documentation commit): backend **105 passed in 11.56s**; all three mobile security/lifecycle scripts, app-config guard, typecheck, Expo Doctor **18/18**, and public Expo config passed.
- Fresh disposable SQLite: `alembic heads`, `upgrade head`, `current`, `downgrade -1`, `upgrade head`, `current` — passed; final revision was `20260810_0005 (head)`.
- `npm run test:task3-security` — passed.
- `npm run test:task4-lifecycle` — passed.
- `npm run test:task5-lifecycle` — passed.
- `node scripts/test-app-config.js` — passed the missing/malformed/non-HTTP(S)/loopback release URL guard.
- `npm run typecheck` — passed.
- `npx expo-doctor` — **18/18 checks passed**.
- Development `npx expo config --type public --json` with dotenv disabled and an explicit loopback development URL — passed; output was written outside the repository.
- `.github/workflows/ci.yml` parsed as YAML and contains separate backend/mobile jobs. A hosted GitHub Actions run is not yet evidence and must be recorded after push.

Earlier exact-tree Task 6 evidence at commit `32186b8`:

- Full backend suite — **105 passed in 6.36s**; a separately materialized exact staged backend also passed all 105 tests.
- Mobile security/lifecycle scripts, typecheck, Expo Doctor, public config, and web export passed.
- Web export bundled 2,223 modules in the final Task 6 run.
- A migrated real Uvicorn HTTP/WebSocket smoke created two sessions, joined an invite, generated mock SVGs, kept the prompt hidden from the guesser, submitted a guess, polled events, issued a single-use WebSocket ticket, and replayed game-scoped events. Recorded result:

```json
{"event_count": 11, "http_lifecycle": "ok", "provider": "mock", "score": 100, "websocket_replay": "ok"}
```

Automated coverage includes authorization/IDOR boundaries, invite/round/guess atomic invariants, generation budgets, provider constructor/timeout/malformed/oversized/error paths, retry provenance, reset restrictions, device-token ownership/generations, notification bounds, WebSocket ticket consumption/replay, two-round lifecycle/statistics, cross-game isolation, deep-link parsing, stale-work retirement, and source-level secret/prompt logging guards.

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

- The local simulator tooling attempt did not finish a current JavaScript bundle. Automated lifecycle checks and web export pass, but this is not simulator UI evidence.
- Local SQLite and the in-process invite limiter are appropriate only for the current single-service development/beta shape. Multi-instance deployment needs PostgreSQL and a shared rate limiter.
- The repository previously reported missing local Git objects during an exact-index archive. On 2026-08-10, the previously named objects were readable and `git fsck --connectivity-only --no-dangling` exited cleanly. Final publication should still verify the pushed remote branch rather than assuming the earlier local issue is permanently resolved.
- `npm ci` prints deprecation warnings in transitive Expo/Metro tooling. They do not fail install, typecheck, Doctor, config, or export.
- Production universal links/app links require domain association files and native configuration; only the custom development scheme and pure parser behavior are currently implemented/covered.

## Release blockers

- Final Task 8 whole-branch review, immutable candidate SHA, clean status/diff/secret/generated-file inspection, hosted CI result, remote branch verification, and PR field are not yet recorded.
- `npm ci`/`npm audit --omit=dev` currently reports **27 advisories: 12 moderate and 15 high** in the Expo/React Native/Metro dependency graph. Suggested automatic resolutions include incompatible major SDK changes. A focused dependency/security triage is required before external distribution; do not run `npm audit fix --force` on the candidate.
- External beta distribution should wait for at least one complete physical iOS two-player pass. Android must either pass or be explicitly removed from scope.
- If the candidate advertises real AI or push, the corresponding live OpenRouter and Expo push checks above are blockers until recorded.
- A PostgreSQL-backed staging deployment is blocked until the migration chain and core lifecycle are executed against that target database.
- Production universal/app links are blocked until their domain association and native handoff are configured and tested; use only the documented development custom scheme until then.

## Final update checklist

At Task 8 completion:

1. Replace the candidate/remote/PR placeholders.
2. Rerun every automatic command against the final SHA and update counts only if measured.
3. Link or identify the hosted CI run without copying secrets.
4. Record dependency-audit disposition.
5. Move completed external/device items into the passed sections with build/device/provider evidence.
6. Leave any unmet item in **Release blockers** with an explicit scope decision.
