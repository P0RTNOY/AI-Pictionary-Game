# AI Pictionary Game

AI Pictionary is a two-player Expo/FastAPI beta. One player writes a prompt, three AI artists produce SVG clues, the other player guesses, and the game records scoring and changes turns.

The repository contains:

- `backend/` — FastAPI, SQLAlchemy, Alembic, AI/notification providers, and pytest coverage.
- `mobile/` — Expo SDK 54, React Native, TypeScript, authenticated API clients, and lifecycle checks.
- `docs/` — beta testing, release-candidate QA, and release evidence.

## Backend: first local run

From a fresh checkout:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
test -e .env || cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The example configuration uses local SQLite, deterministic mock AI, and mock notifications. `AUTO_CREATE_TABLES=true` also keeps the local SQLite schema compatible at startup, but deployable environments must set it to `false` and run Alembic explicitly.

Public checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ai/status
```

Do not commit `.env` or credential values.

## Anonymous beta sessions

`POST /users` creates a local profile and returns an opaque bearer token once. The backend stores only its hash; the mobile app stores the token with the local user ID and sends it on private requests.

Profiles created before session tokens were introduced cannot be recovered insecurely. If the app finds a stored user ID without a token, or the backend confirms that the token is invalid with `401`, it clears that local session and returns to onboarding. A network or server failure keeps the session and shows a retry path.

## AI providers and provenance

`AI_PROVIDER` accepts exactly `mock`, `openrouter`, or `local`. Unknown values fail configuration instead of falling back silently.

### Mock (default)

```bash
AI_PROVIDER=mock
```

Mock mode is deterministic and free. It is suitable for lifecycle testing, not for evaluating drawing quality. Every generated SVG records `provider_used`, and mobile waiting/guess/result screens visibly mark any mock artifact as testing output.

### OpenRouter

Set these in `backend/.env` or the deployment secret store:

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

Restart the backend, open **Beta debug**, and verify the separate rows:

- **AI provider** must say `openrouter`.
- **Judge model** reports the configured OpenRouter judge model.

Create a new round after changing providers. Persisted artifacts keep the provider that actually produced them. If `OPENROUTER_JUDGE_MODEL` is empty, scoring falls back to local similarity. Provider construction, timeout, malformed response, and oversized-response failures leave the round in a recoverable failed state without exposing the prompt or raw provider error.

### Local OpenAI-compatible server

```bash
AI_PROVIDER=local
LOCAL_MODEL_BASE_URL=http://localhost:1234/v1
LOCAL_MODEL_NAME=your-local-model
```

The local provider calls `{LOCAL_MODEL_BASE_URL}/chat/completions`; it does not run inference inside the mobile app. Local-provider scoring uses local similarity. Confirm **AI provider** says `local`; the separate **Judge model** row is configuration information and does not change that behavior.

## Database and migrations

Local defaults:

```bash
DATABASE_URL=sqlite:///./ai_pictionary.db
AUTO_CREATE_TABLES=true
```

Normal schema commands, run from `backend/` with the virtual environment active:

```bash
alembic heads
alembic upgrade head
alembic current
```

The current chain includes provider provenance, anonymous sessions and WebSocket tickets, transition constraints, device-token ownership, and device-token registration generations. Run `alembic downgrade -1` only against a disposable QA database; it is not a normal deployment step.

PostgreSQL-shaped local setup:

```bash
docker compose --profile postgres up -d postgres
export DATABASE_URL=postgresql+psycopg://ai_pictionary:ai_pictionary_dev@localhost:5432/ai_pictionary
cd backend
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The command above uses the compose development credentials only. Use a secret store and a different password outside local development.

## Safe local reset

The preferred reset is **Beta debug → Reset backend local data**. The endpoint is available only when both conditions are true:

- backend `ENV` is `local`, `dev`, `development`, or `test`; and
- backend `DEBUG=true`.

It also requires the current bearer session and an exact confirmation payload. It deletes all rows from the current local/test database in dependency order, clears the process-local notification outbox and invite limiter, and returns the app to onboarding because the current session was deleted. Staging and production receive `404` even if `DEBUG` is accidentally enabled.

**Reset local app state** is different: it best-effort unregisters that installation's push token, retires active work, and clears this device's profile/session/onboarding state. It does not delete backend games or other users.

## Backend validation

```bash
cd backend
source .venv/bin/activate
python -m pytest -q
```

The pytest harness always creates a dedicated `ai-pictionary-pytest-only-*` temporary directory and binds `app.db` to its SQLite file before importing application modules. It removes any inherited `DATABASE_URL` from the test process afterward so Alembic tests can supply their own disposable URLs. Plain `python -m pytest -q` therefore never performs fixture cleanup against the configured application database.

For the disposable migration round trip used by CI, set `DATABASE_URL` to a new SQLite file, then run:

```bash
alembic heads
alembic upgrade head
alembic current
alembic downgrade -1
alembic upgrade head
alembic current
```

## Mobile: first local run

Use Node 20.19.4 or newer within Node 20, or Node 22.13.0 or newer. The pinned `expo-doctor` 1.20.1 enforces that runtime range.

```bash
cd mobile
npm ci
test -e .env.local || cp .env.example .env.local
EXPO_PUBLIC_API_URL=http://localhost:8000 npm start
```

For a physical phone on the same LAN, use the computer's LAN address instead of loopback:

```bash
EXPO_PUBLIC_API_URL=http://YOUR_MAC_IP:8000 npm start -- --host lan
```

Browser preview:

```bash
EXPO_PUBLIC_API_URL=http://localhost:8000 npm run web
```

The local loopback default is intentionally limited to non-release environments. Staging and production Expo config fails closed if `EXPO_PUBLIC_API_URL` is missing, malformed, non-HTTP(S), loopback, or unspecified. Configure it as a plaintext public EAS environment variable for the matching `preview` or `production` environment; it is not a secret.

`EXPO_PUBLIC_API_TIMEOUT_MS` optionally sets the API deadline from 1,000 to 60,000 ms; invalid values use the 15,000 ms default.

## Mobile validation

Run from `mobile/`:

```bash
npm run test:task3-security
npm run test:task4-lifecycle
npm run test:task5-lifecycle
node scripts/test-app-config.js
npm run typecheck
npm run doctor
EXPO_NO_DOTENV=1 EXPO_PUBLIC_APP_ENV=development EXPO_PUBLIC_BUILD_PROFILE=development EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 npx expo config --type public --json
```

CI runs the same security/lifecycle, type, Doctor, config, backend test, and migration checks without provider or push credentials. See [the CI workflow](.github/workflows/ci.yml).

## API and authorization summary

Public endpoints:

- `GET /health`
- `GET /ai/status`
- `POST /users`
- `POST /invites/preview` (capability lookup, rate-limited)

Private HTTP endpoints require `Authorization: Bearer <session token>`. The server derives the actor from that token and enforces profile ownership, game participation, and turn/role checks. Main private routes include profile/game reads, invite creation/join, round creation/read/retry/guess, event polling, WebSocket-ticket issuance, and device-token register/unregister.

Realtime uses a short-lived, game-scoped, single-use ticket:

```text
POST /games/{game_id}/websocket-ticket
WS /ws/games/{game_id}?ticket=...&after_id=...
```

The mobile app deduplicates event IDs, bounds reconnect backoff, and uses authenticated polling as fallback. It never puts the long-lived bearer token in the WebSocket URL.

Legacy direct `POST /games`, `POST /rounds`, and capability-in-path invite routes exist only in authenticated local debug mode. Debug health/data/reset/notification routes also require authenticated local debug mode and are unavailable in deployable environments.

## Push notifications

Local development defaults to:

```bash
NOTIFICATION_PROVIDER=mock
```

Expo delivery requires secrets outside git:

```bash
NOTIFICATION_PROVIDER=expo
EXPO_ACCESS_TOKEN=...
```

Device-token registration and unregister are authenticated. Active token ownership, per-user registrations, fanout, and the diagnostic outbox are bounded. Network delivery occurs after game-state commits; failures are stored with stable redacted messages. Beta debug copies only a short irreversible token fingerprint, never the raw token.

## EAS builds and deployment

```bash
npm install -g eas-cli
eas login
cd mobile
eas build --profile development --platform ios
eas build --profile development --platform android
EXPO_PUBLIC_API_URL=http://YOUR_MAC_IP:8000 npx expo start --dev-client --host lan
```

Remote EAS builds use Continuous Native Generation because `.easignore` excludes the committed local native directories. Preview and production builds need their non-loopback `EXPO_PUBLIC_API_URL` configured before `eas build`.

Deployable backend shape:

```bash
ENV=staging
DEBUG=false
AUTO_CREATE_TABLES=false
DATABASE_URL=postgresql+psycopg://...
CORS_ALLOW_ORIGINS=https://your-preview-origin.example
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=...
NOTIFICATION_PROVIDER=expo
EXPO_ACCESS_TOKEN=...
```

Run `alembic upgrade head` before starting the deployed backend. SQLite is appropriate for local/single-process testing; PostgreSQL remains the intended deployable database target.

## QA and release evidence

- [Beta testing guide](docs/BETA_TESTING.md)
- [Release-candidate QA](docs/RELEASE_CANDIDATE_QA.md)
- [Release readiness evidence](docs/RELEASE_READINESS.md)
