# Release Candidate QA

## EAS Development Build Setup

Install and log in:

```bash
npm install -g eas-cli
eas login
```

Create a development build:

```bash
cd mobile
eas build --profile development --platform ios
eas build --profile development --platform android
```

Run a local dev server for the development build:

```bash
cd mobile
EXPO_PUBLIC_APP_ENV=local EXPO_PUBLIC_BUILD_PROFILE=development EXPO_PUBLIC_API_URL=http://YOUR_MAC_IP:8000 npx expo start --dev-client --host lan
```

Preview/internal build:

```bash
cd mobile
eas build --profile preview --platform ios
eas build --profile preview --platform android
```

Production build:

```bash
cd mobile
eas build --profile production --platform all
```

Expo Go is still useful for quick UI checks. Use a development build for realistic push notifications, native notification taps, and custom-scheme deep-link testing.

## Environment Profiles

Mobile public env vars:

```bash
EXPO_PUBLIC_APP_ENV=local
EXPO_PUBLIC_BUILD_PROFILE=development
EXPO_PUBLIC_API_URL=http://YOUR_MAC_IP:8000
```

Suggested profiles:

- Local LAN: `EXPO_PUBLIC_APP_ENV=local`, `EXPO_PUBLIC_API_URL=http://YOUR_MAC_IP:8000`
- Development build: `EXPO_PUBLIC_BUILD_PROFILE=development`
- Preview/staging: `EXPO_PUBLIC_APP_ENV=staging`, `EXPO_PUBLIC_API_URL=https://api-staging.your-domain.com`
- Production: `EXPO_PUBLIC_APP_ENV=production`, `EXPO_PUBLIC_API_URL=https://api.your-domain.com`

Backend release-candidate env:

```bash
ENV=staging
DEBUG=false
AUTO_CREATE_TABLES=false
DATABASE_URL=postgresql+psycopg://...
CORS_ALLOW_ORIGINS=https://your-preview-app.example
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=...
NOTIFICATION_PROVIDER=expo
EXPO_ACCESS_TOKEN=...
```

Run migrations:

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
```

Health check:

```bash
curl https://your-api.example/health
```

## Manual QA Checklist

- Install development build on iPhone.
- Install development build on Android if available.
- First launch onboarding appears.
- Profile setup creates and persists user.
- Beta debug shows app version, environment, build profile, API URL, and backend health.
- Backend unreachable state appears when `EXPO_PUBLIC_API_URL` is wrong.
- Create invite.
- Share invite.
- Open invite from cold start.
- Open invite while app is already open.
- Join invite after onboarding.
- Self-join is blocked.
- Expired invite is blocked.
- Accepted invite cannot be joined twice.
- Create prompt.
- Generation success shows ready sketches.
- Retry generation after failure.
- Reveal clues and confirm penalty.
- Submit guess.
- Result screen shows score and components.
- Turn switches correctly.
- Push token registers on physical device.
- Send test notification from Beta debug.
- Tap notification opens correct game.
- Backend restart preserves game state.
- App restart preserves user/game state.
- WebSocket reconnects.
- Polling fallback works when WebSocket fails.
- Original prompt is not visible to guesser before result.

## Deep Link QA

```bash
cd mobile
npx uri-scheme open aipictionary://invite/ABC123 --ios
npx uri-scheme open aipictionary://invite/ABC123 --android
```

Expected:

- App opens to Join Invite.
- Invite code is prefilled.
- If profile setup is unfinished, the invite is retained and shown after profile creation.
- If backend is unreachable, user sees a recoverable error and can retry.

## Troubleshooting

Phone cannot reach backend:

- Confirm backend runs with `--host 0.0.0.0`.
- Confirm phone and Mac are on the same network.
- Confirm `EXPO_PUBLIC_API_URL=http://YOUR_MAC_IP:8000`.
- Check firewall/VPN.

Wrong API URL:

- Open Beta debug and inspect API URL/backend health.
- Restart Expo after changing public env vars.

Push token missing:

- Use a physical device.
- Use a development build for real testing.
- Check iOS/Android notification permissions.
- Tap Refresh push token in Beta debug.

Notification not received:

- Confirm `NOTIFICATION_PROVIDER=expo`.
- Confirm `EXPO_ACCESS_TOKEN`.
- Check `/debug/notification-outbox` in non-production debug mode.
- Confirm the token row exists via logs/debug tooling.

Invite link opens app but does not join:

- Check backend health in Beta debug.
- Tap Check on the Join Invite screen.
- Confirm invite is pending and not owned by the current user.

WebSocket disconnected:

- Beta debug should show polling fallback after repeated failures.
- Confirm `GET /games/{game_id}/events` returns events.

Backend CORS issue:

- Set explicit `CORS_ALLOW_ORIGINS` for staging/production.
- Do not rely on wildcard CORS outside local/dev.

Alembic migration issue:

- Confirm `DATABASE_URL` points to the intended database.
- Run `alembic current`.
- Run `alembic upgrade head`.
