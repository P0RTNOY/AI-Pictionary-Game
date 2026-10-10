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

