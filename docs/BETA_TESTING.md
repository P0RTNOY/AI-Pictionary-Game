# Beta Testing Guide

## Local Phone Setup

Run the backend on your LAN:

```bash
cd backend
source .venv/bin/activate
AI_PROVIDER=mock AUTO_CREATE_TABLES=true uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Find your Mac IP:

```bash
ipconfig getifaddr en0
```

Run Expo for a physical phone:

```bash
cd mobile
EXPO_PUBLIC_API_URL=http://YOUR_MAC_IP:8000 npm start -- --host lan
```

Scan the QR code with Expo Go or a development build.

For realistic push notification and native deep-link testing, use an EAS development build:

```bash
cd mobile
eas build --profile development --platform ios
EXPO_PUBLIC_API_URL=http://YOUR_MAC_IP:8000 npx expo start --dev-client --host lan
```

See [RELEASE_CANDIDATE_QA.md](/Users/portnoy/Documents/MobileGame/docs/RELEASE_CANDIDATE_QA.md) for the full release-candidate checklist.

## Two-Phone Invite Flow

1. Open the app on phone A.
2. Finish onboarding and create a profile.
3. Tap Create invite.
4. Tap Share, Copy code, or Copy link.
5. Open the copied `aipictionary://invite/CODE` link on phone B.
6. Finish onboarding/profile setup if needed.
7. Confirm the prefilled invite code and tap Join game.
8. Phone A should show the invite as Joined after refresh or app foreground.

Dev invite format:

```text
aipictionary://invite/CODE
```

Future production invite format:

```text
https://your-domain.com/invite/CODE
```

## Deep-Link Testing

iPhone simulator or physical device:

```bash
npx uri-scheme open aipictionary://invite/ABC123 --ios
```

Android emulator or device:

```bash
npx uri-scheme open aipictionary://invite/ABC123 --android
```

Expected behavior:

- Cold start opens the app and stores the invite until profile setup is complete.
- Already-open app routes to Invites with the code prefilled.
- Own invite shows a friendly message and cannot be joined.
- Expired or accepted invites show status and cannot be joined again.

## Universal Links And App Links

For production:

- iOS: add Associated Domains in the Apple developer portal and EAS config, for example `applinks:your-domain.com`.
- Android: add intent filters for `https://your-domain.com/invite/*` and host a valid `assetlinks.json`.
- Web fallback: create a small landing page at `/invite/{code}` that opens the app link and shows install/dev-build instructions if the app is missing.
- Keep `aipictionary://invite/{code}` for dev and `https://your-domain.com/invite/{code}` for production sharing.

Update before release:

- `mobile/app.json` `ios.bundleIdentifier`
- `mobile/app.json` `android.package`
- App icon and splash assets
- EAS project ID and push credentials
- Production invite domain

## Push Testing

Local mock mode remains default:

```bash
NOTIFICATION_PROVIDER=mock
```

Expo delivery mode:

```bash
NOTIFICATION_PROVIDER=expo
EXPO_ACCESS_TOKEN=...
```

Test flow:

1. Install on a physical device; simulators may not produce push tokens.
2. Create or load a profile.
3. Open Beta debug.
4. Check Push permission and Push token.
5. Tap Refresh push token if needed.
6. Tap Send test notification to this device.
7. Background the app and confirm the notification arrives.
8. Tap the notification. If it includes `game_id`, the app should open that game and route to the correct screen.

Gameplay must continue if permission is denied.

## Manual QA Checklist

- First launch shows onboarding.
- Profile setup creates and persists a local user.
- Create invite generates a code.
- Share invite opens native share sheet.
- Deep link pre-fills Join Invite.
- Own invite cannot be joined.
- Invalid invite shows friendly failure.
- Expired invite cannot be joined.
- Accepted invite cannot be joined twice.
- Create prompt works from the correct turn only.
- Create a prompt manually and confirm the creator sees the same prompt after submit.
- Create a prompt using builder cards.
- Edit the generated prompt before submitting and confirm the edited final text is used.
- Generation success shows ready sketches.
- In OpenRouter/local mode, SVG clues should visibly match the submitted prompt.
- In mock mode, Beta debug should show `mock`; drawings are deterministic test clues and include prompt-derived labels.
- Partial generation failure still allows guessing with ready sketches.
- Retry appears when all sketches fail.
- Guess screen never shows original prompt before result.
- Extra clue warning appears and clue penalty is applied.
- Guess submission produces result.
- Result shows score, clue penalty, matched/missed parts, component scores, and copy action.
- Turn switches after result.
- Push token registers on app launch and foreground.
- Test push notification is queued from Beta debug.
- Notification tap opens the correct game.
- App restart preserves profile and active games.
- Backend restart preserves games in SQLite.
- WebSocket reconnect updates active game.
- Polling fallback still refreshes if WebSocket fails.

## Reset And Migrations

Reset local SQLite:

```bash
cd backend
rm -f ai_pictionary.db ai_pictionary.db-*
alembic upgrade head
```

Run migrations:

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
```

## Troubleshooting

Phone cannot reach backend:

- Confirm backend uses `--host 0.0.0.0`.
- Confirm Expo uses `EXPO_PUBLIC_API_URL=http://YOUR_MAC_IP:8000`.
- Keep phone and Mac on the same network.
- Try `curl http://YOUR_MAC_IP:8000/health` from another machine.
- Check firewall/VPN settings.

WebSocket issues:

- Confirm `GET /games/{game_id}/events` works.
- Watch Beta debug for WebSocket connected vs polling fallback.
- Restart Expo after changing `EXPO_PUBLIC_API_URL`.

Push issues:

- Use a physical device for real tokens.
- Check Beta debug for permission and token.
- Confirm `/debug/send-test-notification` works only when `DEBUG=true`.
- Use `GET /debug/notification-outbox` to inspect mock/Expo attempts.
