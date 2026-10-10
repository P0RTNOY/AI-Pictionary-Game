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

