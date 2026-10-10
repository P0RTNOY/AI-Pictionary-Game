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

