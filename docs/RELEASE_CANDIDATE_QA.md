# Release Candidate QA

Use this checklist against one immutable candidate commit. Record the commit, build IDs, backend deployment, device/OS versions, provider, and pass/fail result in [RELEASE_READINESS.md](RELEASE_READINESS.md). Never record bearer tokens, invite capabilities, API keys, Expo tokens, or `.env` contents.

## Candidate identity

- Candidate commit: `<full SHA>`
- Branch/remote: `<remote branch>`
- Pull request: `<URL or unavailable>`
- Backend deployment/revision: `<identifier>`
- iOS build/device/OS: `<identifier>`
- Android build/device/OS: `<identifier>`
- AI provider: `<mock | openrouter | local>`
- Notification provider: `<mock | expo>`

## Automated preflight

Backend, from `backend/` with the virtual environment active:

```bash
python -m pytest -q
```

The test harness owns a dedicated temporary SQLite database and overrides any inherited `DATABASE_URL` before importing application database code. Fixture cleanup cannot target the local/staging/production application database. Individual migration tests still supply their own disposable URLs.

Disposable SQLite migration round trip:

```bash
MIGRATION_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ai-pictionary-rc.XXXXXX")"
export DATABASE_URL="sqlite:///$MIGRATION_DIR/migrations.db"
export ENV=test
export DEBUG=true
export AUTO_CREATE_TABLES=false
alembic heads
alembic upgrade head
alembic current
alembic downgrade -1
alembic upgrade head
alembic current
```

Mobile, from `mobile/`:

Use Node 20.19.4+ or Node 22.13.0+; CI pins Node 20.19.4 and `expo-doctor` 1.20.1.

```bash
npm ci
npm run test:task3-security
npm run test:task4-lifecycle
npm run test:task5-lifecycle
node scripts/test-app-config.js
npm run typecheck
npm run doctor
EXPO_NO_DOTENV=1 EXPO_PUBLIC_APP_ENV=staging EXPO_PUBLIC_BUILD_PROFILE=preview EXPO_PUBLIC_API_URL=https://api.example.invalid npx expo config --type public --json
EXPO_NO_DOTENV=1 EXPO_PUBLIC_APP_ENV=staging EXPO_PUBLIC_BUILD_PROFILE=preview EXPO_PUBLIC_API_URL=https://api.example.invalid npx expo export --platform web --output-dir /tmp/ai-pictionary-web
```

The repository CI workflow performs the same core checks with mock providers and no external credentials. A green CI run does not substitute for the physical-device, live-provider, push, or target-PostgreSQL checks below.

## Release environment

Example backend shape (place values in the deployment environment, not git):

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

Before backend startup:

```bash
alembic upgrade head
alembic current
```

Verify `GET /health` and `GET /ai/status` after deployment. Confirm all debug data/reset/test-notification routes return `404` in staging/production, including when someone accidentally sets `DEBUG=true`.

Mobile public configuration:

```bash
EXPO_PUBLIC_APP_ENV=staging
EXPO_PUBLIC_BUILD_PROFILE=preview
EXPO_PUBLIC_API_URL=https://api-staging.your-domain.example
```

`EXPO_PUBLIC_API_URL` is public configuration, not a secret. Configure it as a plaintext EAS value in the matching `preview` or `production` environment before building. Release config intentionally fails for missing, malformed, non-HTTP(S), loopback, or unspecified URLs. The native runtime repeats this guard whenever `__DEV__` is false, even if environment labels were omitted at build time.

## EAS build setup

```bash
npm install -g eas-cli
eas login
cd mobile
eas build --profile development --platform ios
eas build --profile development --platform android
```

Internal preview candidates:

```bash
eas build --profile preview --platform ios
eas build --profile preview --platform android
```

Production candidates:

```bash
eas build --profile production --platform all
```

Remote EAS uses Continuous Native Generation because `.easignore` excludes the local native directories. Confirm the uploaded build uses the expected icon/splash, bundle/package identifiers, API URL, environment, build profile, and EAS project before distribution.

## Session and authorization QA

- Fresh onboarding creates a profile and persists a usable bearer session across restart.
- A deliberately incomplete legacy local profile (ID without token) returns to onboarding once.
- Backend `401` clears a rejected session; network/`5xx` failure retains it and offers retry.
- User/profile/game/round/event/device-token routes reject a missing or wrong bearer.
- A participant cannot read another game's private state or events.
- The guesser cannot read `original_prompt` before scoring.
- Invite preview is public/minimal; invite create/join needs the authenticated actor.
- Invite codes remain case-sensitive and are absent from request/error logs.
- WebSocket uses a fresh short-lived ticket, not the bearer token in the URL; reuse and cross-game use fail.

## Two-device lifecycle QA

Run with two fresh sessions after a safe local/test reset or against isolated staging test data:

- Create an invite on device A and join on device B.
- Confirm device A owns the initial turn and device B waits.
- Create a prompt; confirm only the creator can read it before the result.
- Confirm all three artifact rows persist the actual `provider_used`.
- In mock mode, waiting/guess/result screens show **Mock output — testing only**.
- Reveal clues and verify each reveal is persisted before display. Reopen/background the round and confirm the count is retained, then submit one guess and verify the server-stored count determines the penalty and score components.
- Confirm turn change, create a second round on device B, and complete it.
- Confirm game statistics, Home grouping, activity, and badges update on both devices.
- Switch rapidly between two games; stale fetch/poll completions must not overwrite the selected game.
- Background/foreground during round load and mutation; duplicate actions and stale callbacks must not apply.
- Disconnect/reconnect network; WebSocket recovery and polling fallback must remain bounded and avoid duplicate events.
- Restart app and backend; valid session and migrated game state persist.

## Provider QA

In **Beta debug**, treat these as different signals:

- **AI provider** is the selected runtime provider.
- **Judge model** is the configured OpenRouter judge-model row.
- **Round Provider** is persisted artifact provenance.

For live OpenRouter QA:

- set `AI_PROVIDER=openrouter` explicitly and provide the key through the secret store;
- restart and verify **AI provider** says `openrouter`;
- create a fresh round and confirm `provider_used=openrouter` with no mock warning;
- visually review clue quality across all tiers;
- verify judging with the configured judge model and local fallback when that setting is intentionally empty;
- test a controlled provider error and generation retry; and
- confirm per-user/global daily budgets and active-generation rejection are visible and recoverable.

Mock mode can pass lifecycle QA but cannot pass real drawing-quality QA. Local-provider unavailable/malformed/oversized-response behavior is automated; a real local model still needs its own quality run if it will ship.

## Push and notification QA

Use physical devices and an EAS development/preview build:

- grant/deny permissions and confirm gameplay works in both cases;
- register and refresh; debug displays only a token fingerprint;
- send the authenticated local-debug test notification where allowed;
- background the app, receive the notification, and tap through to an authorized game;
- confirm another user's game cannot be opened from crafted notification data;
- rotate identity/reset local app state and verify the old registration is retired;
- confirm one provider/token has only one active owner and per-user fanout stays bounded; and
- inspect provider delivery receipts through approved deployment tooling without copying raw device tokens.

## Deep-link QA

Development scheme:

```bash
npx uri-scheme open 'aipictionary://invite/AbcDef_123-xyz4567890' --ios
npx uri-scheme open 'aipictionary://invite/AbcDef_123-xyz4567890' --android
```

Check cold/warm valid links, malformed/encoded-slash links, self/expired/accepted invites, session-not-ready handling, backend-unreachable recovery, and authenticated private game links. Production universal links/app links are not complete until the domain association files and native entitlements/intent filters are deployed and verified.

## Accessibility and interaction QA

- VoiceOver/TalkBack identifies game rows, invite actions, prompt parts, guess, retry, reset, and color choices.
- Selected color/avatar state is announced and not communicated by color alone.
- Busy actions announce loading and cannot be submitted twice.
- Touch targets are usable on the smallest supported phone.
- Dynamic text does not hide destructive warnings, provider provenance, score, or primary actions.
- Mock warnings remain high contrast in every artifact screen.

## Reset QA

**Reset local app state** must retire realtime/API work, best-effort unregister the current push token, clear this device's session/profile/game/navigation/onboarding state, and return to first launch without deleting backend data.

**Reset backend local data** must require an authenticated session, exact destructive confirmation, local/test `ENV`, and `DEBUG=true`. It clears the current database and process-local notification/debug state, then returns the device to onboarding. It must return `404` in staging/production.

## Exit criteria

Before distributing an external beta candidate:

- final candidate SHA and remote branch are recorded;
- CI and exact local validation are green;
- target-database migration is verified on a disposable copy or staging database;
- at least one physical iOS two-player pass is recorded;
- Android is either passed or explicitly removed from the candidate scope;
- enabled live AI and notification providers are tested with their real credentials;
- cold/warm link behavior is tested for the links actually distributed;
- no raw secret/session/invite/device-token values appear in logs, diffs, screenshots, or reports; and
- every remaining limitation is listed in release readiness with an owner/decision.
