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

