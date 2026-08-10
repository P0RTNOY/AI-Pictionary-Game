# Beta Release Readiness Implementation Plan

> **For Codex:** Execute this plan with `superpowers:subagent-driven-development`. Use a fresh implementer and task reviewer for every task. Follow TDD for behavior changes and preserve the existing unfinished working-tree batch.

**Goal:** Turn the current functional AI Pictionary beta and its unfinished polish batch into a validated, documented, safely deployable beta candidate on `codex/beta-release-readiness`, then commit and publish the branch.

**Architecture:** Keep the existing FastAPI/SQLAlchemy/Alembic backend and Expo/React Native client. Add a minimal opaque bearer-session boundary for anonymous beta profiles so identity is server-verifiable without introducing third-party login. Retain the current provider abstraction and game lifecycle, but make provenance, failure states, realtime ownership, destructive tooling, and release configuration fail safely.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy, Alembic, pytest, Expo SDK 54, React Native, TypeScript, AsyncStorage, Expo Notifications, EAS.

## Global Constraints

- Preserve all valuable committed and uncommitted work; never reset or clean the repository broadly.
- Do not expose, print, stage, or commit `.env` values, API keys, device tokens, or other credentials.
- Do not push to `main`; all work remains on `codex/beta-release-readiness` and is published with a normal non-force push.
- Use focused changes that match the existing architecture. Do not add unrelated product features or a third-party authentication provider.
- Use behavior-first tests for backend changes and run the repository's actual checks. Never suppress safety checks merely to obtain a passing result.
- Keep public invite lookup limited to the information needed to join. Every private user/game/round/event/device-token operation must use server-verified identity and enforce ownership or game participation.
- Existing profiles that predate session credentials may require local re-onboarding; document this one-time beta migration behavior rather than inventing insecure credential recovery.
- Release builds must never silently use a loopback API URL. Missing or loopback production/staging configuration must fail before a candidate is shipped.
- Debug database reset must be limited to local/test execution, be deterministic, clear notification debug state, and never be reachable in staging or production.
- Persist the provider that actually produced a generated SVG. Unknown provider names must fail configuration rather than silently becoming mock; provider initialization failures must produce a recoverable failed round.
- Bound paid generation with database-backed per-user and global daily budgets plus a global active-generation limit; defaults must be safe and environment-configurable without adding a hosted rate-limit dependency.
- Invite capabilities must use the `secrets` module with high entropy. Single-use invite, one-active-round, and one-guess invariants must be enforced atomically or by database constraints, not only sequential application checks.
- Bound untrusted provider response bytes before JSON/SVG parsing. Bound notification-token ownership/fanout and the in-memory diagnostic outbox; keep network delivery out of uncommitted game-state transactions where practical.
- Do not claim external OpenRouter, APNs/physical-device push, or physical two-device QA without actually executing it.

### Task 1: Repository hygiene, Expo compatibility, and build configuration

**Files:**
- Modify: `.gitignore`
- Modify: `mobile/package.json`
- Modify: `mobile/package-lock.json`
- Modify: `mobile/app.json` or introduce the smallest existing-convention Expo config module if runtime validation requires it
- Modify: `mobile/eas.json`
- Verify: `mobile/ios/AIPictionary/Images.xcassets/**`
- Verify: `mobile/assets/**`

**Requirements:**

1. Ignore `graphify-out/` and `.superpowers/sdd/` as generated/scratch output. Remove only the locally generated `graphify-out/` directory after validating it is the exact non-symlink repository child; do not remove source or user data.
2. Run `npx expo install --fix` from `mobile` so Expo SDK 54 dependencies are resolved by Expo's supported workflow. Review every manifest/lockfile change.
3. Remove the `appConfigFieldsNotSyncedCheck` suppression. Resolve any resulting Expo Doctor issue through configuration or native asset consistency, not by disabling the check.
4. Ensure iOS, Android, and web icon/splash configuration points to real, correctly sized branded artwork. Do not ship the blank legacy iOS icon or a featureless splash square as the visible logo. Preserve good artwork and make native/configured assets consistent.
5. Make staging and production configuration reject a missing or loopback `EXPO_PUBLIC_API_URL`; local development may retain a documented loopback default. Keep public configuration out of secret storage and document how EAS receives the value.
6. Run `npm run typecheck`, `npx expo-doctor`, and an Expo config export/bundle smoke check supported by the installed toolchain.

### Task 2: Provider provenance, configuration, and recoverable generation failures

**Files:**
- Modify: `backend/app/ai.py`
- Modify: `backend/app/services.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/orm_models.py`
- Modify: `backend/app/database.py`
- Modify: `backend/alembic/versions/3ada93e0ae67_add_provider_used_to_generatedsvg.py`
- Modify/Add: focused files under `backend/tests/`

**Requirements:**

1. Start with failing tests covering: actual provider provenance on successful generation; retry provenance; unknown provider configuration; provider-constructor failure; public error redaction; and an existing SQLite schema upgraded through the supported compatibility path.
2. Validate provider names (`mock`, `openrouter`, `local`) and expose complete, accurate AI status including local-model configuration without leaking credentials.
3. Construct providers inside the generation error boundary. Any initialization, timeout, malformed response, or provider error must move the round to a recoverable failed state instead of leaving it stuck in `generating`.
4. Persist `provider_used` from the provider instance that actually generated each SVG. Preserve safe behavior for historical null records and update it on retries.
5. Read OpenRouter/local-model responses through a byte-bounded transport path before JSON parsing and SVG sanitization. Preserve existing timeouts and reject oversized/malformed bodies with the same recoverable public failure semantics.
6. Do not log original prompts or persist/broadcast raw provider exception text. Log actionable server-side context with safe exception classification; return/store a stable user-facing failure message.
7. Keep the Alembic migration chain linear and validate upgrade/downgrade. Ensure the existing local SQLite startup compatibility policy handles `provider_used` without silently diverging from the ORM.
8. Run focused tests and the complete backend test suite.

### Task 3: Server-verified beta sessions and route authorization

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/services.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/orm_models.py`
- Modify: `backend/app/database.py`
- Add: a new Alembic revision after `3ada93e0ae67`
- Modify/Add: focused files under `backend/tests/`
- Modify: mobile API client/session files under `mobile/src/api/`
- Modify: `mobile/App.tsx`
- Modify: `mobile/src/hooks/useGameEvents.ts`

**Requirements:**

1. Start with failing backend tests demonstrating current client-asserted identity/IDOR behavior for user, game, round, event, WebSocket, mutation, and device-token operations.
2. Add a minimal anonymous beta session: create an opaque random token when a profile is created, return it once to the client, store only a secure hash in the database, and authenticate HTTP requests with `Authorization: Bearer`.
3. Derive the actor from the verified token on all private routes. If compatibility fields remain in payloads, require them to match the actor. Enforce game participation and role/turn checks at every sibling read and mutation.
4. Authenticate WebSocket subscriptions with the session token, reject non-participants before accepting private game events, and do not put private prompts in event payloads.
5. Store the token in AsyncStorage alongside the local user ID, configure the API client before private calls, and re-onboard safely when an old profile lacks a session token. Never log or render the token.
6. Keep invite-code lookup intentionally public but disclose only the minimum join-preview fields. Require an authenticated actor to create or join an invite.
7. Replace invite-code generation with a high-entropy `secrets` capability and add bounded lookup/join attempt protection appropriate to the existing single-service beta architecture.
8. Enforce configurable database-backed per-user/global daily generation budgets and a global active-generation ceiling before any paid generation job is created. Remove or strictly localize the legacy `/rounds` path so it cannot bypass authenticated membership, turn, or budget controls.
9. Add/update the migration and SQLite compatibility behavior for nullable legacy token hashes. Document that legacy local profiles must re-onboard rather than providing insecure recovery.
10. Run focused auth, quota, invite, WebSocket, full backend, and mobile type checks.

### Task 4: Debug reset and notification-token lifecycle safety

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/services.py`
- Modify: `backend/app/notifications.py`
- Modify: `backend/app/models.py`
- Modify/Add: focused files under `backend/tests/`
- Modify: `mobile/src/api/deviceTokens.ts`
- Modify: `mobile/src/api/debug.ts`
- Modify: `mobile/App.tsx`
- Modify: `mobile/src/screens/DebugScreen.tsx`
- Modify: notification-related mobile hooks as required

**Requirements:**

1. Start with failing tests proving reset is unavailable in staging/production and that token ownership/reset lifecycle is deterministic.
2. Restrict destructive debug/database reset to local/test environments with debug enabled. Do not expose data-bearing debug endpoints in deployable beta environments.
3. Clear database rows in a foreign-key-safe deterministic order and clear in-memory notification outbox/debug state. Return only a safe summary.
4. Make device-token registration authenticated and enforce at most one active owner for a provider/token pair. Add an authenticated unregister operation.
5. Enforce a small configurable active-token limit per user, cap the diagnostic outbox, and ensure notification side effects do not hold an uncommitted game-state transaction. Keep aggregate delivery work bounded without introducing a new hosted queue dependency.
6. Before local logout/reset or identity replacement, best-effort unregister the current device token, retire realtime/polling work, and then clear session/user/game/local navigation state. Backend reset must also leave the client in a clean onboarding state.
7. Remove raw push tokens from copied diagnostics; use only a short irreversible fingerprint where correlation is useful.
8. Make destructive UI copy explicit and disable duplicate actions while reset is in progress; preserve useful error recovery.
9. Run focused tests, full backend tests, and mobile type checking.

### Task 5: Mobile lifecycle, realtime, deep-link, and interaction robustness

**Files:**
- Modify: `mobile/App.tsx`
- Modify: `mobile/src/hooks/useGameEvents.ts`
- Modify: `mobile/src/api/games.ts`
- Modify: `mobile/src/api/rounds.ts`
- Modify: relevant screens/components under `mobile/src/screens/` and `mobile/src/components/`
- Modify: `mobile/src/types/game.ts`

**Requirements:**

1. Prevent stale polling or fetch completions for an old game/user from overwriting a newly selected game. Cancel or generation-gate in-flight refreshes during game switch, reset, backgrounding, and unmount.
2. Reset WebSocket `lastId` and deduplication state on game/user changes, ignore callbacks from retired sockets, use the authenticated event API, and keep bounded reconnect/backoff plus polling fallback without duplicate subscriptions or runaway timers.
3. Make cold/warm deep-link handling safe for valid invite/game links and malformed/expired entities. Never navigate into private game state before identity and authorization are ready.
4. Show provider provenance from persisted `provider_used`; any mock-generated artifact must be unmistakably labeled even in a misconfigured deployable build, while avoiding repetitive modal interruptions.
5. Fix duplicate submission/loading gaps, including generation retry, invite/game actions, prompts, guesses, profile saves, and reset actions. Keep buttons disabled with clear progress and recovery.
6. Improve obvious accessibility gaps: descriptive labels for invites/guesses/game rows/actions, selected state not communicated by color alone, adequate touch targets, and meaningful disabled/loading state.
7. Run mobile type checking, Expo Doctor, config validation, and bundle/startup smoke tests.

### Task 6: Core lifecycle regression coverage and local integration QA

**Files:**
- Modify/Add: backend behavioral tests under `backend/tests/`
- Add only minimal mobile pure-function tests if the existing repository supports them without a new test stack
- Modify source only when this task discovers a reproducible defect

**Requirements:**

1. Add/extend behavior-focused backend coverage for the two-player lifecycle: create profiles/sessions, create invite, join, turn ownership, create round, generate/persist SVG and provider provenance, wait/read without prompt leakage, guess/score, result, next turn, second round, statistics, and cross-game isolation.
2. Exercise WebSocket authorization/event replay and polling-event fallback with two distinct sessions. Prove reconnect cursors do not leak or skip another game's events.
3. Add database-backed regression coverage for atomic single-use invite consumption, at most one active round per game, and at most one guess per round. Exercise concurrent requests where the local database/runtime can do so reliably and always test the underlying uniqueness/transition invariant.
4. Cover generation budgets, malformed/oversized provider responses, provider timeouts/errors, mock behavior, retry, and local-provider unavailability without startup failure.
5. Validate deep-link parsing through existing pure functions or an Expo-supported local invocation; do not add a large new mobile test dependency solely for this task.
6. Start the backend against a disposable migrated database and execute an HTTP/WebSocket smoke flow where practical. Attempt simulator QA if installed runtimes are available; record automated, simulator, structural, external-credential, and physical-device evidence separately.
7. Run the full backend suite and mobile validation after every discovered fix.

### Task 7: CI, documentation reconciliation, and release evidence

**Files:**
- Add: `.github/workflows/ci.yml` if no equivalent CI exists
- Modify: `README.md`
- Modify: `docs/BETA_TESTING.md`
- Modify: `docs/RELEASE_CANDIDATE_QA.md`
- Add: `docs/RELEASE_READINESS.md`
- Modify: environment examples/config docs only as implementation requires

**Requirements:**

1. Add a focused CI workflow using the repository's package managers that runs backend tests and migration checks plus mobile install/typecheck/Expo Doctor checks. Do not include secrets or live-provider calls.
2. Reconcile every setup/config/provider/debug/reset/build instruction with the final code. Remove stale `Submitting prompt` guidance and describe separate provider/judge debug rows accurately.
3. Document session-token re-onboarding, API URL requirements, migrations, safe local reset scope, mock provenance warnings, provider setup, and exact local validation commands.
4. Create `docs/RELEASE_READINESS.md` with evidence sections: Passed automatically, Passed locally/simulator, Requires external credentials, Requires physical-device QA, Known non-blocking issues, and Release blockers. Include only results actually executed and leave candidate SHA/remote/PR fields ready for final update.
5. Ensure a new developer can run backend and mobile without relying on hidden local state. Never document or copy credential values.
6. Run documentation searches for removed UI labels and configuration drift, then rerun representative documented commands.

### Task 8: Final independent review, validation, commits, and publication

**Files:**
- Modify only files required by final review findings
- Finalize: `docs/RELEASE_READINESS.md`

**Requirements:**

1. Run an independent whole-branch review against the branch merge base. Fix and re-review every Critical/Important correctness, security, migration, lifecycle, or release issue.
2. Run final validation: full backend tests; configured lint/type checks; backend startup smoke; Alembic heads/current plus clean upgrade and previous-revision upgrade/downgrade on disposable databases; mobile clean dependency consistency, typecheck, Expo Doctor, Expo config, and bundle/startup smoke; repository `git diff --check`; final secret/generated-file/status inspection.
3. Perform all simulator/two-player/provider/device checks the environment genuinely allows. Record limitations honestly and update the release-readiness evidence with exact final commands/results.
4. Organize all intended changes into focused conventional commits after inspecting staged diffs and excluding `.env`, generated output, credentials, and unrelated files. Preserve existing commit `cd63f3f` in ancestry.
5. Push `codex/beta-release-readiness` to `origin` with upstream tracking, verify the remote branch, and create a pull request to `main` if authenticated GitHub tooling is available and validation is green.
6. Finish with a clean working tree or explicitly identify only intentional ignored local state. Provide the requested comprehensive release report.
