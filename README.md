# AI Pictionary Game

Mobile-first async multiplayer AI Pictionary.

Two local users can create a game, take turns writing weird prompts, generate three SVG clue drawings, guess the original prompt, receive a semantic score, and pass the turn back. The backend now persists state in SQLite, so games survive backend restarts.

## Structure

- `backend/` - FastAPI, SQLite persistence, game services, AI providers, sanitizer, tests.
- `mobile/` - Expo React Native app with API clients, screens, components, and game types.

## Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

For free local development, keep:

```bash
AI_PROVIDER=mock
```

Run:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

SQLite is created automatically at `backend/ai_pictionary.db` when `AUTO_CREATE_TABLES=true`.

Health:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ai/status
```

## Database And Migrations

Local SQLite default:

```bash
DATABASE_URL=sqlite:///./ai_pictionary.db
AUTO_CREATE_TABLES=true
```

Alembic is available for production-style schema management:

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
alembic downgrade -1
alembic current
```

Reset local SQLite:

```bash
rm -f ai_pictionary.db ai_pictionary.db-*
alembic upgrade head
```

Postgres example:

```bash
docker compose --profile postgres up -d postgres
export DATABASE_URL=postgresql+psycopg://ai_pictionary:ai_pictionary_dev@localhost:5432/ai_pictionary
cd backend
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For production, set `AUTO_CREATE_TABLES=false` and run migrations during deploy.

## OpenRouter Mode

Set:

```bash
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=...
OPENROUTER_MODEL_CONFUSING=openai/gpt-5-nano
OPENROUTER_MODEL_CONFUSING_EFFORT=low
OPENROUTER_MODEL_BALANCED=deepseek/deepseek-v3.2
OPENROUTER_MODEL_LITERAL=openai/gpt-5.2
OPENROUTER_MODEL_LITERAL_EFFORT=high
OPENROUTER_JUDGE_MODEL=openai/gpt-5-nano
```

Do not commit `.env`.

## Local Model Mode

`AI_PROVIDER=local` is a backend-to-local-server placeholder. It expects a local OpenAI-compatible chat server:

```bash
AI_PROVIDER=local
LOCAL_MODEL_BASE_URL=http://localhost:1234/v1
LOCAL_MODEL_NAME=your-local-model
```

This does not run heavy inference inside the mobile app.

## Backend Tests

```bash
cd backend
source .venv/bin/activate
pytest -q
```

Tests cover users, games, turn validation, generation success, partial generation failure, generation retry, game stats, scoring, sanitizer safety, event creation, invites, debug endpoints, Alembic bootstrap, prompt safety, and Expo notification provider behavior.

## Mobile Setup

```bash
cd mobile
npm install
EXPO_PUBLIC_API_URL=http://localhost:8000 npm start
```

For a physical phone, use your Mac LAN IP:

```bash
EXPO_PUBLIC_API_URL=http://192.168.1.114:8000 npm start -- --host lan
```

The beta flow now starts with a short onboarding sequence, then asks for a display name/avatar. Use **Create invite** or **Join** on Home to create/copy an invite code/link or join another player by code.

For a repeatable physical-phone test plan, see [docs/BETA_TESTING.md](/Users/portnoy/Documents/MobileGame/docs/BETA_TESTING.md).
For release-candidate build QA, see [docs/RELEASE_CANDIDATE_QA.md](/Users/portnoy/Documents/MobileGame/docs/RELEASE_CANDIDATE_QA.md).

Mobile beta polish included:

- Home sections for Your Turn, Waiting, and Completed.
- Opponent display name/avatar, status pill, last activity text, and new-turn badge.
- Prompt builder cards for character/object, action, setting, and twist.
- Per-artist waiting status and retry if every artist fails.
- Guess screen that keeps the original prompt hidden, warns before extra clues, and confirms very short guesses.
- Result screen with score label, clue penalty, component scores, matched/missed parts, game stats, and copyable result text.
- Pull-to-refresh on Home, background refresh when the app returns active, WebSocket reconnect with polling fallback, and a small Beta debug screen.
- Haptics-ready feedback through `expo-haptics`; failures are ignored on unsupported devices/simulators.
- Native dev deep links in the form `aipictionary://invite/{code}` open the Join Invite screen and prefill the code.

Push notifications:

- The app requests notification permission after a local user exists.
- If granted, it registers the Expo push token with `POST /device-tokens`.
- If denied or unavailable, gameplay continues normally.
- Notification taps try to open the related game when `game_id` is present in notification data.

SVG generation modes:

- `AI_PROVIDER=mock` is for fast Expo/local testing. It now renders prompt-derived labels and simple scene structure, but it is still not real art.
- `AI_PROVIDER=openrouter` or `AI_PROVIDER=local` should be used when judging whether clues visually match the submitted prompt.
- Beta debug shows the active AI provider so testers know whether they are seeing mock or real generation.

Mobile environment files:

- Copy `mobile/.env.example` to `mobile/.env.local` for local runs.
- Set `EXPO_PUBLIC_API_URL` to your LAN/staging/production backend.
- Set `EXPO_PUBLIC_APP_ENV` to `local`, `development`, `staging`, or `production`.
- Set `EXPO_PUBLIC_BUILD_PROFILE` to `local`, `development`, `preview`, or `production`.

Expo/EAS:

```bash
npm install -g eas-cli
eas login
cd mobile
eas build --profile development --platform ios
eas build --profile development --platform android
EXPO_PUBLIC_API_URL=http://YOUR_MAC_IP:8000 npx expo start --dev-client --host lan
```

Expo Go is still useful for quick local UI checks. Use an EAS development build for real push-notification and native deep-link testing.

## Main API

- `POST /users`
- `GET /users/{user_id}`
- `POST /games`
- `GET /users/{user_id}/games`
- `GET /games/{game_id}`
- `GET /games/{game_id}/stats?user_id=...`
- `POST /invites`
- `GET /invites/{code}`
- `POST /invites/{code}/join`
- `POST /device-tokens`
- `POST /games/{game_id}/rounds`
- `GET /rounds/{round_id}`
- `POST /rounds/{round_id}/retry-generation`
- `POST /rounds/{round_id}/guess`
- `GET /games/{game_id}/events?after_id=...`
- `WS /ws/games/{game_id}`
- `GET /ai/status`
- `GET /debug/health/full` when `DEBUG=true`
- `GET /debug/events` when `DEBUG=true`
- `GET /debug/games` when `DEBUG=true`
- `GET /debug/notification-outbox` when `DEBUG=true`
- `POST /debug/send-test-notification` when `DEBUG=true`

Legacy `POST /rounds` remains for compatibility.

## Realtime

The backend exposes:

```text
WS /ws/games/{game_id}?user_id=...&after_id=...
```

Messages are wrapped as:

```json
{"type": "event", "event": {"id": 1, "event_type": "round.ready_to_guess"}}
```

The mobile app deduplicates by event ID, reconnects on disconnect, and falls back to polling `GET /games/{game_id}/events?after_id=...`.

## Push Notifications

`POST /device-tokens` stores Expo-style device tokens. Configure:

```bash
NOTIFICATION_PROVIDER=mock
# or
NOTIFICATION_PROVIDER=expo
EXPO_ACCESS_TOKEN=...
```

The backend records notification attempts/results in `notification_attempts`. Notification sending is non-blocking for game actions; failures are stored and logged.

Notifications are triggered when:

- opponent creates a prompt
- round is ready to guess
- opponent guessed
- turn changes
- invite is accepted

Expo push delivery is implemented in `ExpoPushNotificationProvider`.

## Auth Upgrade Path

Current users are local anonymous profiles. The `users` table includes:

- `display_name`
- `avatar_emoji`
- `avatar_color`
- `auth_provider`
- `auth_subject`

Recommended production path:

1. Keep `users.id` as the app profile ID.
2. Add Apple/Google/Supabase/Firebase auth on mobile.
3. Store provider identity in `auth_provider` and `auth_subject`.
4. Use backend auth middleware to map verified JWT claims to the app user.
5. Keep game/round services using app user IDs.

## Deployment Notes

Recommended beta backend targets:

- Render, Fly.io, Railway, or a small VPS Docker deployment.
- Use `AI_PROVIDER=openrouter` for real SVG generation.
- Keep secrets in platform env vars, not `.env` in git.
- Set `CORS_ALLOW_ORIGINS` to your deployed app/dev origins instead of `*`.

SQLite is fine for local beta testing, but not ideal for multi-instance production. Migration plan:

1. Move `DATABASE_URL` to Postgres.
2. Run Alembic migrations.
3. Keep the service layer unchanged.
4. Move file/blob storage for generated SVGs to object storage if needed.

Docker:

```bash
docker compose up --build backend
docker compose --profile postgres up --build
```

Production checklist:

- `ENV=production`
- `DEBUG=false`
- `AUTO_CREATE_TABLES=false`
- `DATABASE_URL=postgresql+psycopg://...`
- `CORS_ALLOW_ORIGINS=https://your-domain.example`
- `AI_PROVIDER=openrouter`
- `OPENROUTER_API_KEY=...`
- `NOTIFICATION_PROVIDER=expo`
- `EXPO_ACCESS_TOKEN=...`
- Run `alembic upgrade head` before starting the app.

Staging should use the same shape with `ENV=staging`, `DEBUG=false`, `AUTO_CREATE_TABLES=false`, explicit `CORS_ALLOW_ORIGINS`, and a staging `DATABASE_URL`.

Mobile builds:

- Expo Go works for local development.
- For beta distribution, create an Expo development build or EAS build.
- Configure Expo push credentials before enabling real push delivery.
- `mobile/eas.json` includes `development`, `preview`, and `production` profiles.

Current beta limitations:

- Invite links use `aipictionary://invite/CODE` in dev. Production universal links/app links should later use `https://your-domain.com/invite/CODE`.
- Realtime still uses database-backed event polling behind the WebSocket loop. It is reliable enough for local beta, but a production deployment should move to a dedicated pub/sub or Postgres notification channel.
- SQLite is best for single-instance local/dev beta. Use Postgres before running multiple backend instances.
- Push notifications are structurally ready and mockable locally; production delivery requires Expo credentials, EAS/project configuration, and device testing.

## Safety

Generated SVG is treated as untrusted input. The backend parses SVG with `defusedxml`, strips scripts, event handlers, external URLs, remote references, and disallowed tags before storing/rendering.

Challenge prompts are normalized and checked by a content-safety placeholder before generation. The current implementation blocks obvious markup/script payloads and enforces prompt length; replace `backend/app/safety.py` with stronger moderation before public launch.
