# Task 5 implementation report

Status: DONE

Commit: `590bb0d fix: harden mobile lifecycle and realtime`

## What changed

- Added abortable, generation-aware identity/game request scopes and latest-completion gates in `mobile/App.tsx`; game/user work is retired on switch, reset, background, and unmount.
- Rebuilt authenticated game realtime handling around per-game/user connection generations, fresh cursor/dedupe state, retired-socket rejection, abortable WebSocket tickets, bounded 8-second connection deadlines, capped exponential reconnect delay, and one non-overlapping polling fallback that stops on recovery.
- Added strict cold/warm app-link parsing for invite capabilities and UUID game links. Links queue until a verified local session is ready; game access is fetched through the authenticated API and friendly 401/403/404 handling does not expose private state.
- Made game/list/event/stats/invite/round/user/WebSocket-ticket API calls accept `AbortSignal`.
- Derived artifact provenance from persisted `provider_used`. Mock artifacts now show a high-contrast `Mock output — testing only` banner in every build on waiting, guessing, and result views; provider information is rendered inline without modal spam.
- Added synchronous ref guards plus abort-on-unmount for prompt creation, generation retry, guesses, invite actions, profile saves, game opens, test pushes, and reset confirmations. Loading and disabled states now cover the relevant controls.
- Improved accessible button busy state, descriptive game/invite/guess/prompt labels, 48px color targets, and visible checkmark plus accessibility selected state for avatar colors.
- Added `mobile/scripts/test-task5-lifecycle.js` with executable request-scope, deep-link, provenance, and source contract checks.

## TDD evidence

- RED: `npm run test:task5-lifecycle` failed because `mobile/src/requestScope.ts` did not exist.
- GREEN: the same command passed after the lifecycle/deep-link/provenance implementation.

## Validation executed

- `npm run test:task5-lifecycle` — passed.
- `npm run test:task4-lifecycle` — passed.
- `npm run test:task3-security` — passed.
- `npm run typecheck` — passed.
- `node scripts/test-app-config.js` — passed release API URL guard.
- `npx expo-doctor` — 18/18 checks passed (rerun after final code changes).
- `EXPO_PUBLIC_APP_ENV=development EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 npx expo config --type public` — passed and emitted the expected public development config.
- `EXPO_PUBLIC_APP_ENV=development EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 npx expo export --platform web --output-dir <validated /tmp directory>` — passed after final code changes; 2,186 modules bundled to `/tmp/mobilegame-task5-final-export.gCoLgV`.
- `CI=1 EXPO_PUBLIC_APP_ENV=development EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 npx expo start --web --port 19007`, followed by `curl --fail --max-time 15 http://127.0.0.1:19007/` — served the AI Pictionary HTML shell; Metro was then stopped with Ctrl-C.
- `git diff --cached --check` — passed before commit.

## Files committed

- `mobile/App.tsx`
- `mobile/package.json`
- `mobile/scripts/test-task5-lifecycle.js`
- `mobile/src/requestScope.ts`
- `mobile/src/utils/deepLinks.ts`
- `mobile/src/utils/providerProvenance.ts`
- `mobile/src/api/{ai,games,invites,rounds,users,websocketTickets}.ts`
- `mobile/src/components/Buttons.tsx`
- `mobile/src/hooks/useGameEvents.ts`
- `mobile/src/screens/{CreateRound,Debug,Guess,Home,Invite,Profile,Result,Waiting}Screen.tsx`
- `mobile/src/styles.ts`
- `mobile/src/types/game.ts`

## Remaining risks / unverified behavior

- No iOS/Android simulator, physical-device accessibility review, two-device notification/deep-link test, or real network-transition test was executed in this task.
- WebSocket and AppState lifecycle behavior is structurally and type validated but still needs simulator/device QA under real suspend/resume and connectivity loss.
- Unrelated pre-existing WIP in `README.md`, `backend/app/ai.py`, `backend/app/services.py`, and `docs/BETA_TESTING.md` remains unstaged and was not modified or committed by Task 5.

## Review follow-up

Commit: `b5b31a2 fix: close mobile lifecycle review gaps`

- Replaced warm game-link suppression with a latest-target coordinator: a newer target aborts the previous open, failed targets remain retryable, successful duplicate suppression is time-bounded and size-bounded, and queued state is retained until the current target settles.
- Added dedicated latest-operation and action-context gates so game/background/home transitions abort active work, reject stale screen callbacks, and cannot leave or overwrite the selected-game loading state.
- Made every API request use a composed caller-signal/default-timeout deadline with listener/timer cleanup.
- Kept polling active across repeated WebSocket flaps until the socket remains healthy for the recovery threshold; polling requests have explicit deadlines.
- Added deterministic regression coverage for A-to-B target supersession, retry after transient failure, stale loading completion, stale/background action rejection, repeated fake-socket flapping, and never-settling request deadlines.

Follow-up validation:

- `npm run test:task5-lifecycle` — passed after a deliberate RED on brief-reopen fallback behavior.
- `npm run test:task4-lifecycle` — passed.
- `npm run test:task3-security` — passed.
- `npm run typecheck` — passed.
- `node scripts/test-app-config.js` — passed.
- `npx expo-doctor` — 18/18 checks passed against the committed tree.
- Development public Expo config — emitted the expected app environment and loopback API URL.
- Web export — 2,254 modules bundled successfully to `/tmp/mobilegame-task5-followup-export.uvKU7w` against the committed tree.
- Live Expo web smoke — HTTP 200 with the AI Pictionary HTML shell; server stopped cleanly.
- Exact-tree backend validation — 94 tests passed.

## Second review follow-up

Commit: `07124df fix: preserve pending mobile work safely`

- Added the coordinator's missing post-yield pre-run guard, so request-then-retire never starts retired work.
- Centralized game-open retirement into explicit `preserve-pending` and `clear-pending` modes. Backgrounding retains the latest target for resume, while Home, invite navigation, reset, and unmount clear pending/opening state and invalidate aborted await tails.
- Added an immediate action-context guard to profile creation/update callbacks. Foreground, lifecycle epoch, identity/game context, and the screen abort signal are checked before requests, before storage writes, after awaited storage, and before synchronous credential/client-state commits.
- Added deterministic regressions for immediate retirement, background/resume retry, explicit Home cancellation, and a deferred profile save resolving after background before passive cleanup.

Second follow-up validation:

- Task 5, Task 4, and Task 3 harnesses — passed.
- TypeScript typecheck — passed.
- `node scripts/test-app-config.js` — passed.
- Expo Doctor — 18/18 checks passed.
- Development public Expo config — emitted the expected app environment and loopback API URL.
- Web export — 2,255 modules bundled successfully to `/tmp/mobilegame-task5-review2-export.ceJxmd`.
- Live Expo web smoke — HTTP 200 with the AI Pictionary HTML shell; server stopped cleanly.
