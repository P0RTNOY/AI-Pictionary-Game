# Task 6 — Core lifecycle regression and local integration QA

## Scope and baseline

- Starting commit: `07124df`
- Task 6 commit: `67ae9c1` (`fix: harden beta integration lifecycle`)
- Task 6 security follow-up: `dd6d71d` (`fix: redact WebSocket tickets in server logs`)
- Reviewer follow-up: `32186b8` (`test: strengthen integration lifecycle evidence`).
- Branch: `codex/beta-release-readiness`
- Preserved pre-existing unstaged work in `README.md`, `backend/app/ai.py`, `backend/app/services.py`, and `docs/BETA_TESTING.md`.
- Baseline backend suite before Task 6 changes: `94 passed in 6.17s`.

## Coverage added

`backend/tests/test_task6_integration_qa.py` adds behavior-focused coverage for:

- Authenticated two-player onboarding, invite preview/join, initial turn enforcement, mock SVG generation, persisted `provider_used`, prompt secrecy for the guesser, guess/score/result, turn change, second round by the other player, aggregate statistics, event privacy, and a second isolated game.
- Authenticated polling and WebSocket replay for two different games and sessions, independent per-game cursors, exact game filtering, and single-use WebSocket tickets.
- Idle WebSocket disconnect observation so a closed socket does not retain a server task indefinitely.
- Local-provider malformed JSON, oversized declared response, read timeout, HTTP error, and unavailable endpoint behavior, including stable public failure state and redacted event payloads.
- Missing local-provider configuration that leaves `/health` available, fails generation recoverably, and then retries successfully with mock provenance.
- In-process Alembic upgrade isolation for existing application loggers.

Existing database-backed tests executed in the full suite continue to cover:

- Concurrent single-use invite acceptance: `test_invite_pending_to_accepted_consumption_is_atomic`.
- Concurrent one-active-round transition and notification: `test_concurrent_round_creation_has_one_transition_and_one_notification`.
- Concurrent one-guess transition and notification pair: `test_concurrent_guess_submission_has_one_transition_and_one_notification_pair`.
- Direct unique-index enforcement: `test_database_metadata_enforces_one_guess_and_one_active_round`.
- Per-user daily, global daily, and global active-generation budgets.
- Provider constructor failure, provenance replacement on retry, bounded streamed responses, and mock generation behavior.

`mobile/scripts/test-task5-lifecycle.js` extends the existing pure deep-link checks with extra path segments, encoded slash injection, malformed percent encoding, and an unsupported URL scheme. No new mobile test framework or dependency was added.

## Reproducible defects found and fixed

### Idle WebSocket retained the server task

The first real Uvicorn smoke completed HTTP and WebSocket behavior, but a single graceful interrupt hung at `Waiting for background tasks to complete`. The WebSocket loop only polled the database, sent new events, and slept; when no event followed a peer close, it never consumed the ASGI disconnect message.

RED:

```text
pytest tests/test_task6_integration_qa.py::test_idle_websocket_observes_client_disconnect_without_waiting_for_an_event
1 failed (asyncio.TimeoutError)
```

Fix: replace the blind polling sleep with a bounded `websocket.receive()` wait. A disconnect returns immediately; timeout preserves the 750 ms polling cadence.

GREEN:

```text
1 passed in 0.45s
```

The repeated real-server smoke logged `websocket.disconnected` and completed application shutdown after the first interrupt.

Reviewer follow-up strengthened this regression so the first `receive()` blocks beyond the 750 ms poll interval and is cancelled by the timeout, while the next receive reports a disconnect. The test now proves the healthy idle poll survives, the cancelled receive task is cleaned up, the disconnect is consumed on the next poll, and the server does not close an already-disconnected socket.

```text
pytest tests/test_task6_integration_qa.py::test_idle_websocket_observes_client_disconnect_without_waiting_for_an_event
1 passed in 1.28s
```

### Alembic disabled existing application loggers in-process

Running the auth migration tests before the provider redaction test reproducibly caused the latter to lose its structured generation-failure records. Alembic's `fileConfig()` defaulted to `disable_existing_loggers=True`; the normal alphabetical suite order masked the problem.

RED:

```text
pytest tests/test_task6_integration_qa.py::test_in_process_alembic_upgrade_preserves_existing_application_loggers
1 failed: application_logger.disabled was True
```

Fix: configure Alembic logging with `disable_existing_loggers=False`.

GREEN/order regression:

```text
1 passed in 0.46s
29 passed in 2.85s
```

### Local-provider configuration is applied before lifespan startup

The original missing-local-provider test reused the module `client` fixture, whose lifespan had already started before the test changed `AI_PROVIDER`. The reviewer follow-up first wrapped the app lifespan and demonstrated the ordering gap:

```text
1 failed: startup_entered was False
```

The test now sets the local-provider environment first and only then creates a fresh `TestClient`. It asserts the observed lifespan starts, `/health` remains available, `/ai/status` reports the local provider as unconfigured, the round enters the stable public failure state, and retrying under the mock provider recovers it.

```text
pytest tests/test_task6_integration_qa.py::test_missing_local_provider_configuration_does_not_block_startup_and_retry_recovers
1 passed in 0.60s
```

## Automated evidence

Backend:

- `backend/.venv/bin/python -m pytest -q` — `104 passed in 5.73s` after both fixes.
- Materialized exact staged backend (with unrelated `ai.py` and `services.py` WIP reversed in a disposable copy): `104 passed in 6.19s`.
- After the WebSocket-log redaction follow-up: full backend `105 passed in 6.65s`; materialized exact staged backend `105 passed in 5.46s`.
- Reviewer follow-up: focused Task 6 file `11 passed in 1.97s`; full backend `105 passed in 6.36s`; materialized exact staged backend `105 passed in 7.00s`.
- Focused Task 6/auth/provider runs exercised the new lifecycle, WebSocket, concurrency, budget, and provider matrix.
- `git diff --check` — clean before staging.

Mobile:

- `npm run test:task3-security` — passed.
- `npm run test:task4-lifecycle` — passed.
- `npm run test:task5-lifecycle` — passed with the extended deep-link cases.
- `node scripts/test-app-config.js` — release API URL guard passed.
- `npm run typecheck` — passed.
- `npx expo-doctor` — `18/18 checks passed`.
- `npx expo config --type public` — exited successfully; output was written outside the repository.
- `npx expo export --platform web --output-dir <disposable /tmp directory>` — web bundle exported successfully (`2223` modules).

## Migrated real-server smoke

Two fresh disposable SQLite databases were upgraded through the full Alembic chain to `20260810_0005 (head)`. Uvicorn was started with `AUTO_CREATE_TABLES=false`, `AI_PROVIDER=mock`, and mock notifications. The smoke used real HTTP and WebSocket clients to execute:

- `/health`
- two profile/session creations
- authenticated invite creation and join
- authenticated round creation and background mock generation
- guesser read with prompt hidden
- authenticated guess and score
- event polling with prompt absence assertion
- WebSocket ticket issuance, connection, and event replay

Final structured result:

```json
{"event_count": 11, "http_lifecycle": "ok", "provider": "mock", "score": 100, "websocket_replay": "ok"}
```

After the fix, one interrupt produced `websocket.disconnected`, `Application shutdown complete`, and `Finished server process` without a forced second interrupt.

The live Uvicorn handshake initially revealed that `--no-access-log` does not suppress its WebSocket acceptance line, which included the query string. A `uvicorn.error` log filter now replaces only the `ticket` value with `%5BREDACTED%5D` while retaining the game path and `after_id`. A focused RED/GREEN test and a real-server connection confirmed the raw single-use ticket no longer appears in that line.

## Simulator and device evidence

### Bounded booted-Simulator attempt

- Xcode `26.6` (`17F113`).
- iOS `26.5` simulator runtime.
- Booted iPhone 17 Pro simulator (`iPhone18,1`).
- `com.portnoy.aipictionary.beta` is installed on that simulator.
- A disposable Alembic-head SQLite backend was started on `127.0.0.1:8000` with mock generation and notifications.
- Two unrelated pre-existing Metro servers occupied ports `8081` and `8082`, so the current branch's Expo dev-client server was started on `8083`; neither unrelated process was modified.
- The `exp+ai-pictionary` development-client URL was delivered to the installed app. Simulator logs confirmed `AIPictionary` connected to `127.0.0.1:8083` and requested `/node_modules/expo/AppEntry.bundle`.
- The app remained on `Loading from Metro...`. A bounded host bundle request received zero bytes before timing out, while Metro's final buffered progress advanced to about 43% but never completed before the attempt was stopped.
- Therefore current-JavaScript startup, onboarding, game lifecycle, and in-app deep-link parsing were **not** visually verified. This is a bounded environment/tooling limitation, not a passing Simulator result.
- Temporary screenshots were captured at `/tmp/mobilegame-task6-simulator.BZ0s9H/after-launch.png`, `/tmp/mobilegame-task6-simulator.BZ0s9H/direct-launch.png`, and `/tmp/mobilegame-task6-simulator.BZ0s9H/exp-scheme-launch.png`.
- The task-owned backend, Metro server, and app process were stopped afterward. Ports `8000` and `8083` were free; the pre-existing listeners on `8081` and `8082` remained running.

### Not available

- Android emulator was not on `PATH` and was not present at the expected local Android SDK emulator path.

### Requires external credentials or services

- Live OpenRouter generation/judging was not executed.
- A real OpenAI-compatible local model server was not executed; its unavailable/error paths were exercised with bounded local transports.
- PostgreSQL behavior was not executed; SQLite constraint/concurrency and migration paths were executed.
- Expo push delivery/APNs was not executed; mock notification behavior remains covered by the suite.

### Requires physical-device QA

- Physical iOS/Android launch and two-device play.
- Push permission and delivery behavior.
- Warm/cold production universal-link handoff.
- Network interruption/recovery on real devices.

## Files in Task 6 scope

- `backend/tests/test_task6_integration_qa.py` (new)
- `backend/app/main.py`
- `backend/alembic/env.py`
- `mobile/scripts/test-task5-lifecycle.js`

This report is generated task scratch under the already-ignored `.superpowers/sdd/` directory and is intentionally not part of the release commit.

## Repository object-store observation

An attempted exact-index `git archive` could not materialize the tree because the local repository already references missing objects, including missing blobs and a missing tree (`3bbb316c…`). `git fsck --no-dangling` reports the condition. The first focused commit succeeded. A second commit was initially blocked by the missing blob for `backend/app/__init__.py`; the current worktree file hashed exactly to the expected missing object ID (`a502a370…`), so that identical blob alone was restored with `git hash-object -w`, after which the commit succeeded. No history rewrite, fetch, reset, or speculative reconstruction was performed. Final publication should still verify/fetch the remaining object graph before push.
