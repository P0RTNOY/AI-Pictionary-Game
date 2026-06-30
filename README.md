# AI Pictionary MVP

Turn-based AI Pictionary prototype based on the attached game idea.

One player writes a strange situation. The backend asks three AI artist tiers for SVG clues, sanitizes those SVGs, and exposes them to the mobile app. The guess is scored semantically. For local development, the backend uses deterministic mock artists and a local scoring heuristic when no OpenRouter key is configured.

## Project Structure

- `backend/` - FastAPI app, round endpoints, SVG sanitizer, mock/OpenRouter AI services.
- `mobile/` - Expo React Native app for the core create/wait/guess/result loop.

## Run Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Optional real model setup:

```bash
cp .env.example .env
# Fill OPENROUTER_API_KEY and model env vars.
```

Model IDs are intentionally env-driven because OpenRouter availability changes over time.

## Run Mobile App

```bash
cd mobile
npm install
EXPO_PUBLIC_API_URL=http://localhost:8000 npm start
```

For a physical device, replace `localhost` with your computer's LAN IP address.

## API

- `POST /rounds` - create a challenge and start SVG generation.
- `GET /rounds/{round_id}` - poll round status and generated sketches.
- `POST /rounds/{round_id}/guess` - submit a guess and receive a score.

## Safety Notes

AI-generated SVG is treated as untrusted input. The backend parses SVG with `defusedxml`, drops disallowed tags and attributes, removes event handlers, rejects external references, and enforces a 40KB limit before the app renders anything.
