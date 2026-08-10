// Keep this synchronized with the OpenRouter judge timeout in backend/app/ai.py.
export const JUDGE_PROVIDER_TIMEOUT_MS = 35_000;
export const SUBMIT_GUESS_TIMEOUT_MS = JUDGE_PROVIDER_TIMEOUT_MS + 10_000;
