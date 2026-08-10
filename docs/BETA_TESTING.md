# Beta Testing Guide

This guide covers local mock-provider testing and the manual checks that need a simulator or physical device. Release evidence and outstanding external checks are tracked in [RELEASE_READINESS.md](RELEASE_READINESS.md).

## Local backend and mobile

Prepare and start the backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
test -e .env || cp .env.example .env
alembic upgrade head
AI_PROVIDER=mock AUTO_CREATE_TABLES=true uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Prepare the app:

```bash
cd mobile
npm ci
test -e .env.local || cp .env.example .env.local
EXPO_PUBLIC_API_URL=http://YOUR_MAC_IP:8000 npm start -- --host lan
```

Find a Mac Wi-Fi address with:

```bash
ipconfig getifaddr en0
```

Use `http://localhost:8000` for an iOS simulator or browser on the same Mac. A physical phone must use a reachable LAN address, and the phone and Mac must be on the same network.

Expo Go is useful for quick UI checks. A development build is required for realistic native push, notification-tap, and custom-scheme testing:

```bash
cd mobile
eas build --profile development --platform ios
EXPO_PUBLIC_API_URL=http://YOUR_MAC_IP:8000 npx expo start --dev-client --host lan
```

If Expo starts in development-build mode when Expo Go was intended, press `s` to switch launch targets. If LAN discovery fails, `npx expo start --tunnel` is a debugging option; the backend URL still must be reachable from the device.

## Session-token migration behavior

The current app needs both a stored local user ID and its opaque bearer token. A profile created by an older build may have only the user ID. That profile intentionally has no credential-recovery path and must re-onboard once.

Expected behavior:

- missing user ID or token clears the incomplete local session and shows onboarding;
- a verified backend `401` clears the rejected session and shows onboarding; and
- network, parsing, or backend `5xx` failures retain the session and show a retryable recovery state.

Never copy a bearer token into a test report. **Copy full debug info** excludes it and includes only a short irreversible push-token fingerprint.

## Two-device invite flow

1. Complete onboarding and create a profile on device A.
2. Tap **Create invite**, then share/copy its link or case-sensitive code.
3. Open the link on device B, or paste the code in **Join**.
4. Complete onboarding on device B if needed; the pending invite should remain available afterward.
5. Preview and join the invite.
6. Refresh/foreground device A and confirm that the game appears.

Development invite links use:

```text
aipictionary://invite/{case-sensitive-code}
```

New invite codes are URL-safe high-entropy capabilities. Do not lowercase them or put them in logs. Six-character legacy codes remain readable during migration.

## Deep-link testing

Optional simulator/emulator invocation:

```bash
cd mobile
npx uri-scheme open 'aipictionary://invite/AbcDef_123-xyz4567890' --ios
npx uri-scheme open 'aipictionary://invite/AbcDef_123-xyz4567890' --android
```

Expected behavior:

- cold start retains the invite until a verified session is ready;
- warm start opens the invite screen with the code prefilled;
- malformed links are ignored safely;
- own, expired, accepted, or missing invites show a recoverable message; and
- a private game link is fetched with the authenticated session before navigation.

Production universal links/app links still require Apple Associated Domains, Android intent filters/`assetlinks.json`, and a real web fallback domain. The custom `aipictionary://` scheme is the current development path.

## Clean local two-player lifecycle

For a deterministic reset, use an already-authenticated app while the backend is running with local/test `ENV` and `DEBUG=true`:

1. On device A, open **Beta debug** and tap **Reset backend local data**.
2. Read the destructive confirmation: this removes every user, game, round, invite, event, notification record, WebSocket ticket, and local debug-outbox entry in that database.
3. Confirm device A returns to onboarding.
4. On device B, use **Reset local app state** (or accept the expected re-onboarding after its deleted session receives `401`).
5. Create two fresh profiles.
6. Create an invite on device A and join from device B.
7. Confirm the first creator sees **Your turn** and the other player sees **Waiting for first prompt**.
8. Submit a distinctive manual prompt from the creator.
9. Confirm the creator continues to see that prompt while the guesser never sees the original prompt before scoring.
10. In mock mode, confirm every artifact view shows the prominent **Mock output — testing only** warning and the persisted round provider is `mock`.
11. Submit a guess, inspect score/components, and confirm the turn switches.
12. Create and complete a second round from the other player.

Do not use prompt bodies or backend logs as tracing evidence. Prompt telemetry is intentionally redacted. Use round IDs, game IDs, event IDs, the **AI provider** row, and persisted artifact provenance instead.

## Beta debug interpretation

The important AI rows are separate:

- **AI provider** — runtime provider selection (`mock`, `openrouter`, or `local`).
- **Judge model** — configured OpenRouter judge model, or `local_similarity` when none is configured.
- **Artist models** — configured artist tier/model names.
- **Round Provider** — persisted `provider_used` for the selected artifact.

When `AI_PROVIDER=mock` or `AI_PROVIDER=local`, scoring is local similarity even if an unused OpenRouter judge-model value remains visible as configuration. Use **AI provider** and **Round Provider** to establish who generated the clue.

Other useful rows include API URL, backend health, WebSocket/polling state, last event, push permission, and push registration fingerprint. Debug data/reset/test-notification endpoints require a bearer and local debug backend; deployable staging/production returns `404`.

## OpenRouter drawing QA

Mock output validates flow, not drawing quality. To test real generation, configure the backend explicitly without recording the key value:

```bash
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=...
OPENROUTER_JUDGE_MODEL=openai/gpt-5-nano
```

Then:

1. Restart the backend.
2. Confirm **AI provider** is `openrouter` and **Judge model** is the intended configured model.
3. Create a new round; do not reuse mock artifacts.
4. Confirm each completed artifact persists `provider_used=openrouter` and has no mock warning.
5. Evaluate prompt-to-image quality, guess scoring, retry after a controlled provider failure, and usage/budget behavior.

If `AI_PROVIDER=openrouter` is set without `OPENROUTER_API_KEY`, startup health remains available but generation fails recoverably. Unknown provider names fail configuration instead of silently using mock.

## Local-model QA

Point the backend at an already-running OpenAI-compatible chat server:

```bash
AI_PROVIDER=local
LOCAL_MODEL_BASE_URL=http://localhost:1234/v1
LOCAL_MODEL_NAME=your-local-model
```

Confirm **AI provider** says `local`, create a new round, and verify `provider_used=local`. Missing/unreachable/malformed local endpoints should leave the round recoverable and must not prevent `/health` from working.

## Push testing

Local mock notification mode:

```bash
NOTIFICATION_PROVIDER=mock
```

Real Expo delivery needs a physical device/development build plus a backend secret:

```bash
NOTIFICATION_PROVIDER=expo
EXPO_ACCESS_TOKEN=...
```

Test flow:

1. Create/load a session on a physical device and grant notification permission.
2. Open **Beta debug** and confirm push registration shows a fingerprint, not a raw token.
3. Tap **Refresh push token**, then **Send test notification**.
4. Background the app and confirm delivery.
5. Tap a notification with `game_id`; confirm the authenticated game opens.
6. Reset local app state and confirm the old registration no longer receives later notifications.

Gameplay must continue if notification permission is denied or delivery fails. The local debug outbox and notification attempts are actor-scoped and bounded.

## Manual QA checklist

- First launch and one-time legacy-profile re-onboarding behave as documented.
- Profile create/edit loading states prevent duplicate submissions.
- Invite create/preview/join handles valid, self, invalid, expired, and already-used capabilities.
- Cold and warm invite links wait for session readiness.
- Prompt manual entry and prompt-part randomization preserve the final edited value.
- Only the current-turn participant can create a round.
- Provider failure gives a recoverable retry; duplicate retries are disabled while pending.
- Mock artifacts are visibly labeled on waiting, guess, and result screens.
- The guesser cannot read the original prompt before result.
- Extra clue confirmation and penalty work.
- Guess submission is single-action and turn/result/statistics update correctly.
- Switching games, going Home, backgrounding, and resuming do not apply stale request results.
- WebSocket reconnect and authenticated polling fallback do not duplicate events.
- App/backend restart preserves valid sessions and migrated game state.
- Buttons expose useful accessibility labels, selected state, and disabled/loading state.
- Local app reset unregisters push best-effort and clears only this installation.
- Backend local reset is destructive, authenticated, and unavailable in staging/production.

## Troubleshooting

Phone cannot reach backend:

- Confirm Uvicorn uses `--host 0.0.0.0`.
- Confirm `EXPO_PUBLIC_API_URL` uses the Mac LAN IP, not `localhost`.
- Verify the phone and Mac share a network and check firewall/VPN settings.
- Try `curl http://YOUR_MAC_IP:8000/health` from another machine.

Wrong API URL or release config failure:

- Restart Expo after changing `EXPO_PUBLIC_*` values.
- Preview/production rejects missing, malformed, non-HTTP(S), loopback, and unspecified URLs by design.
- Configure `EXPO_PUBLIC_API_URL` as a plaintext EAS environment value for the matching build environment.

WebSocket or stale-screen issue:

- Confirm authenticated `GET /games/{game_id}/events` works.
- Check **Realtime** and **Last event** in Beta debug.
- Reopen the game or return Home; active work should retire and polling should remain bounded.

Push issue:

- Use a physical device and development build.
- Check OS permission and the registration fingerprint.
- Confirm the backend is local debug for the test-notification action.
- Do not put raw Expo tokens in reports or logs.

Migration issue:

```bash
cd backend
source .venv/bin/activate
alembic heads
alembic current
alembic upgrade head
```

For deployable environments, keep `AUTO_CREATE_TABLES=false` and migrate before starting the app.
