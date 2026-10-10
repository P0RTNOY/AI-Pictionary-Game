# Task 3 Report: Server-verified beta sessions and route authorization

## Outcome

Implemented anonymous beta bearer sessions, server-derived actors for private HTTP and WebSocket routes, owner/participant/role authorization, capability-safe invites, database-backed generation admission limits, atomic single-transition protections, SQLite/PostgreSQL-compatible invariants, and mobile session persistence/wiring.

Focused commit: `99b3ad5 feat: secure beta sessions and game routes`.

Unrelated reset/debug, provider-warning, accessibility, documentation, and other UI WIP remains unstaged.

## TDD evidence

### RED

Command (from `backend/`):

```text
./.venv/bin/pytest -q tests/test_auth_security.py -k 'onboarding_returns or private_http_routes or invalid_bearer or invite_lookup_and_join_attempts or invite_pending_to_accepted or per_user_daily or global_daily or global_generating or database_metadata or runtime_schema'
```

Exact result:

```text
FFFFFFFFFFFFFFFFF                                                        [100%]
17 failed, 7 deselected in 39.93s
```

The failures showed that client-writable provider identity was accepted; missing/invalid credentials did not produce bearer 401s; events remained public; invite attempts were unbounded; both synchronized invite joins succeeded; all three generation budgets were absent; and the session, guess, and active-round indexes were missing.

### GREEN

Focused security suite (from `backend/`):

```text
./.venv/bin/pytest -q tests/test_auth_security.py
............................                                             [100%]
28 passed in 4.42s
```

Full working-tree backend suite:

```text
./.venv/bin/pytest -q
....................................................................     [100%]
68 passed in 9.01s
```

Exact staged-tree backend suite:

```text
/Users/portnoy/Documents/MobileGame/backend/.venv/bin/pytest -q
..................................................................       [100%]
66 passed in 19.27s
```

The staged tree has two fewer tests because the existing unstaged `test_infra.py` reset/debug WIP is intentionally excluded.

## Security and behavior changes

- `POST /users` now returns `{user, access_token, token_type: "bearer"}` once. Tokens use `secrets.token_urlsafe(32)` (256 bits of source entropy); only SHA-256 hashes are stored in nullable, unique, indexed `users.session_token_hash`.
- `UserCreate` forbids client-supplied `auth_provider` and `auth_subject`.
- Private HTTP routes use FastAPI bearer authentication and a generic `401` plus `WWW-Authenticate: Bearer`. Profile reads/updates/game lists are owner-only; game, stats, round, and event reads are participant-only.
- Compatibility actor fields are optional. When supplied, they must equal the authenticated actor; mobile no longer sends them for authorization.
- Round creation requires participant/current-turn ownership; generation retry requires the prompt creator/current turn; guessing requires the designated guesser.
- WebSockets validate the `access_token` query parameter and game participation before `accept`; streams are game-participant scoped.
- Direct `POST /games` and legacy `POST /rounds` require both an authenticated actor and an explicit local/test debug environment. They return `404` outside local debug.
- Invite capabilities use `secrets.token_urlsafe(24)` (192 bits), preserve case and URL-safe characters, and fit the widened 64-character schema. Public preview returns only `code`, `creator_user_id`, `status`, and `expires_at`; authenticated create/join responses remain full.
- Lookup/join attempts share an in-process per-client-host sliding-window limit. `X-Forwarded-For` is ignored. Attempt count, window, and maximum tracked sources are positive configurable values.
- Invite capability values are redacted from backend request logging and mobile error telemetry.
- A database admission-gate row is updated before generation counts, serializing budget admission across service processes. Limits are per-user daily 25, global daily 200, and global generating 10 by default. Retry does not consume a new daily round but uses the active-generation ceiling.
- Invite pending-to-accepted, round activation, and ready-to-guessed transitions use conditional writes/constraints. Losing conflicts return `409` before duplicate events, notifications, or background scheduling.
- Hidden prompts are no longer revealed when viewer identity is absent and are removed from latest-round logs.
- Mobile persists the access token beside the user ID in AsyncStorage, configures a module-level bearer credential before private calls, clears incomplete/401-rejected legacy sessions, and uses the session token for WebSockets.
- The unused local-opponent onboarding path was removed so a created session token is not discarded.

## Migration

Added revision `20260810_0003` after `3ada93e0ae67`:

- nullable unique/indexed `users.session_token_hash`;
- widened `game_invites.code` to 64 characters;
- `generation_admission_gate` singleton table;
- unique guess-per-round index;
- partial unique active-round-per-game index for `generating` and `ready_to_guess`, using SQL supported by SQLite and PostgreSQL.

Disposable SQLite validation creates a legacy user at revision `3ada93e0ae67`, upgrades to head, verifies the nullable hash/indexes/gate and preserved legacy row, downgrades to `3ada93e0ae67`, verifies removal, then downgrades to base. Exact focused result:

```text
tests/test_auth_security.py::test_auth_migration_preserves_legacy_users_and_round_trips_sqlite PASSED
1 passed in 4.21s
```

## Mobile validation

Working tree and exact staged tree both ran:

```text
npm run typecheck
> ai-pictionary-mobile@0.1.0 typecheck
> tsc --noEmit
```

Exit status: `0`.

## Files in the focused commit

- Backend config/schema/runtime: `backend/.env.example`, `backend/app/config.py`, `backend/app/db.py`, `backend/app/main.py`, `backend/app/models.py`, `backend/app/orm_models.py`, `backend/app/services.py`
- Migration/tests: `backend/alembic/versions/20260810_0003_server_verified_sessions.py`, `backend/tests/test_auth_security.py`, `backend/tests/test_game_flow.py`
- Mobile session/API: `mobile/App.tsx`, `mobile/src/api/client.ts`, `deviceTokens.ts`, `games.ts`, `invites.ts`, `rounds.ts`, `users.ts`
- Mobile consumers: `mobile/src/hooks/useGameEvents.ts`, `usePushNotifications.ts`, `mobile/src/screens/CreateGameScreen.tsx`, `CreateRoundScreen.tsx`, `GuessScreen.tsx`, `InviteScreen.tsx`, `WaitingScreen.tsx`, `mobile/src/types/game.ts`, `mobile/src/utils/deepLinks.ts`

## Self-review

- Confirmed access tokens and session hashes are absent from logs, normal user serialization, events, and all responses except the one onboarding response.
- Confirmed invite, round, and guess synchronized concurrency tests produce one success, one `409`, one stored transition, and no duplicate transition event/notification fanout.
- Confirmed quota rejection occurs before round flush/background task registration and uses stable `429`/`503` codes.
- Confirmed the exact index excludes the pre-existing reset/debug and provider/UI WIP, then validated the index via `git write-tree` and a disposable archive.
- `git diff --cached --check` is clean.

## Remaining concerns / intentionally deferred

- PostgreSQL execution was not available. PostgreSQL-compatible partial-index predicates and `ON CONFLICT` syntax are present, while real migration/concurrency execution was verified on SQLite only.
- The invite attempt limiter is intentionally per-process for the single-service beta; a horizontally scaled deployment would require a shared limiter.
- Legacy rows with a null token hash have no recovery endpoint and must re-onboard, by design.
- Device-token unregister/transfer lifecycle remains Task 4 scope.

## Review amendment: capability logging, debug isolation, migration compatibility, and startup recovery

### Amendment RED

Focused backend review regressions (from `backend/`):

```text
.venv/bin/pytest -q tests/test_task3_security_amendment.py
FFFFFFFFFF                                                               [100%]
10 failed in 0.77s
```

The failures covered the missing WebSocket ticket endpoint, 32-character invite codes that did not fit the legacy schema, unauthenticated debug endpoints and forged notification targets, and the Docker access log still being enabled.

Mobile security/source regression (from `mobile/`):

```text
npm run test:task3-security
Error: ENOENT: no such file or directory, open '.../mobile/src/sessionBootstrap.ts'
```

Exit status: `1`. The deterministic startup decision helper and safe ticket/fixed-invite wiring did not yet exist. Inspection of commit `99b3ad5` also found the prompt-bearing `console.log` and reporter metadata that the source regression now prohibits.

### Amendment GREEN

Focused Task 3 backend suite:

```text
.venv/bin/pytest -q tests/test_auth_security.py tests/test_task3_security_amendment.py
........................................                                 [100%]
40 passed
```

Full working-tree backend suite:

```text
.venv/bin/pytest -q
........................................................................ [ 90%]
........                                                                 [100%]
80 passed in 6.41s
```

Mobile validation:

```text
npm run test:task3-security
task3 security source checks passed

npm run typecheck
> tsc --noEmit

npx expo-doctor
18/18 checks passed. No issues detected!
```

### Amendment changes

- Replaced the long-lived WebSocket bearer query with a 60-second, high-entropy, single-use ticket. Only its SHA-256 hash is stored; issuance is authenticated and game-scoped, consumption is an atomic conditional update, membership is rechecked before accept, and failure remains the same generic WebSocket close.
- Mobile obtains a fresh ticket immediately before every socket connection or reconnect. Ticket and invite capabilities are absent from custom reporter metadata. The Docker Uvicorn command disables its default access log.
- Invite preview and join now use fixed `POST /invites/preview` and `POST /invites/join` targets with the code in JSON. The legacy capability paths require both local debug mode and a bearer and return `404` elsewhere. New invite codes use `token_urlsafe(16)`, providing 128 bits of source entropy in 22 URL-safe characters.
- All debug reads, notification sends, and reset require bearer authentication and an explicit local/test debug environment. Reads and notification data are actor-scoped; notification sends cannot forge a target user and supplied games must include the actor.
- Removed prompt bodies, builder parts, returned prompts, request payloads, and prompt-bearing error metadata from round-creation logs/reporting. The source regression rejects those patterns.
- Migration `20260810_0003` now reconciles legacy duplicate guesses and multiple active rounds deterministically before adding unique indexes. Conflict rows and original statuses remain in compatibility archive tables at head and are fully restored before downgrade. The SQLite light-migration uses equivalent archives and ordering.
- Startup now clears credentials only for missing/incomplete storage or a verified `401`. Storage errors, network failures, parse failures, and backend `5xx` retain credentials and route to a retryable session-recovery screen. A pure decision helper is behavior-tested from Node.

### Amendment migration evidence

`test_upgrade_reconciles_and_archives_legacy_conflicts_then_downgrade_restores_them` starts at `3ada93e0ae67` with two guesses for one round and two active rounds for one game. It verifies one deterministic canonical row/status plus archived conflicts after upgrade; creates a new 22-character invite; downgrades to `3ada93e0ae67`; verifies both guesses and both original statuses are restored and the invite remains; then verifies equivalent SQLite light-migration reconciliation.

PostgreSQL execution remains unverified because no disposable PostgreSQL service was available. The Alembic SQL uses portable window functions and predicates supported by the repository's SQLite/PostgreSQL targets.

### Amendment exact staged-tree validation

Exported Git tree `7ae7bfe51a9cfd3870ab21a9af17a05a423cef8d` to a disposable directory and ran validation there with only the repository's installed runtimes linked in:

```text
backend: 80 passed in 5.38s
mobile source/security: task3 security source checks passed
mobile typecheck: tsc --noEmit (exit 0)
Expo Doctor: 18/18 checks passed
git diff --cached --check: clean
```

The staged index excludes the unrelated SVG schema additions, mobile local-reset wiring, mock-provider UI warnings, accessibility/UI polish, and documentation edits still present in the working tree.

## Second review amendment: recovery routing, legacy compatibility, and bounded tickets

### Second amendment RED

Focused backend regression command (from `backend/`):

```text
.venv/bin/pytest -q tests/test_task3_security_amendment.py
..F.F......FF.F                                                          [100%]
5 failed, 10 passed in 1.46s
```

The failures proved that fixed invite endpoints rejected a valid six-character legacy code, repeated ticket issuance stored two rows for one user/game, the global reset API and service were still exposed, and migration canonicalization marked the newest active round failed.

Mobile regression command (from `mobile/`):

```text
npm run test:task3-security
TypeError: restoredSessionDestination is not a function
```

Exit status: `1`. The retry-success destination transition did not exist.

### Second amendment GREEN

```text
.venv/bin/pytest -q tests/test_task3_security_amendment.py
...............                                                          [100%]
15 passed in 3.09s

.venv/bin/pytest -q tests/test_auth_security.py tests/test_task3_security_amendment.py
...........................................                              [100%]
43 passed in 3.60s

.venv/bin/pytest -q
........................................................................ [ 88%]
.........                                                                [100%]
81 passed in 17.60s

npm run test:task3-security
task3 security source checks passed

npm run typecheck
> tsc --noEmit

npx expo-doctor
18/18 checks passed. No issues detected!
```

### Second amendment changes

- A successful stored-session load or retry now clears startup error state and routes to `home`, or to `invites` when an invite is pending. The pure helper regression exercises transient failure followed by successful retry and a usable destination.
- Removed `/debug/reset-local-data`, `reset_local_database`, and their old infrastructure tests from Task 3. The unrelated uncommitted Task 4 mobile reset UI remains untouched; Task 4 must implement reset with ticket/archive lifecycle semantics.
- Fixed invite preview/join schemas accept legacy codes from six characters while generation remains exclusively `token_urlsafe(16)` (22 URL-safe characters, 128 bits of source entropy). Exact case and URL-safe punctuation are preserved.
- Active-round reconciliation now keeps `ORDER BY created_at DESC, id DESC`, exactly matching `latest_round_orm`. Tests cover a genuinely newer round and an equal-timestamp deterministic ID tie.
- WebSocket tickets have expiry and consumption indexes plus a unique `(user_id, game_id)` database invariant. Issuance deletes all consumed/expired rows, rotates a still-valid pair in place, and handles insert races without allowing duplicate storage. Repeated abandonment, consumption, expiry, rotation, and concurrent issuance remain bounded to user/game relationships while consumption stays atomic and single-use.

### Second amendment migration evidence

The disposable `3ada93e0ae67` round-trip now includes a pending mixed-case six-character invite, distinct-age and equal-timestamp active-round conflicts, and duplicate SQLite light-migration ticket rows. After upgrade, the normal authenticated game endpoint returns the newest active round, fixed invite endpoints preview and join the exact legacy code, and ticket indexes/invariants exist. Downgrade restores original rows/statuses and removes the ticket table/indexes; the subsequent SQLite light path deterministically reconciles active rounds and ticket duplicates.

### Second amendment exact staged-tree validation

Exported final Git tree `c84ca470441aaee57d796647965f9f073f9cf63f` and validated it independently:

```text
backend: 81 passed in 10.71s
mobile source/security: task3 security source checks passed
mobile typecheck: tsc --noEmit (exit 0)
Expo Doctor: 18/18 checks passed (exit 0)
git diff --cached --check: clean
```

The exact index contains 11 Task 3 amendment files. Uncommitted Task 4 reset UI and unrelated Task 5/UI/provider/documentation work remain outside it.

## Final review amendment: linearizable ticket rotation and consumption

### CAS race RED

```text
.venv/bin/pytest -q tests/test_task3_security_amendment.py::test_websocket_ticket_rotation_wins_against_paused_old_ticket_consumption
F                                                                        [100%]
1 failed in 0.78s
```

The deterministic regression paused consumption after selecting the old ticket hash, rotated the single user/game row to a new hash, then resumed consumption. Before the fix, the old ticket incorrectly authenticated the creator because the conditional update matched only row ID, consumption state, and expiry.

### CAS race GREEN

The consume update now includes `ticket_hash == presented_hash` in the same atomic predicate. Rotation therefore makes the old consumer's update affect zero rows and return the existing generic `401`, without consuming the newly issued ticket.

```text
.venv/bin/pytest -q tests/test_task3_security_amendment.py -k websocket_ticket
....                                                                     [100%]
4 passed, 12 deselected in 0.97s

.venv/bin/pytest -q tests/test_auth_security.py tests/test_task3_security_amendment.py
............................................                             [100%]
44 passed in 3.11s

.venv/bin/pytest -q
........................................................................ [ 87%]
..........                                                               [100%]
82 passed in 12.42s
```

A verbose diagnostic combined run also passed all 44 tests in 58.22s while checking a suspected hang. No pytest, Python test, or Uvicorn process remained; a subsequent clean timed rerun returned to 3.11s, indicating transient SQLite/Alembic contention rather than leaked test threads or sessions.

### CAS exact staged-tree validation

Exported Git tree `933eb7d389b2a63dfa482a9e92a6345d36da712d` containing only the service CAS line and synchronized regression:

```text
backend: 82 passed in 5.84s
git diff --cached --check: clean
```

Mobile files were not touched by this final amendment. Unrelated working-tree WIP remains outside the index.
