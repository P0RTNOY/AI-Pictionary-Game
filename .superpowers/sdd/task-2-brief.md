### Task 2: Provider provenance, configuration, and recoverable generation failures

**Files:**
- Modify: `backend/app/ai.py`
- Modify: `backend/app/services.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/orm_models.py`
- Modify: `backend/app/database.py`
- Modify: `backend/alembic/versions/3ada93e0ae67_add_provider_used_to_generatedsvg.py`
- Modify/Add: focused files under `backend/tests/`

**Requirements:**

1. Start with failing tests covering: actual provider provenance on successful generation; retry provenance; unknown provider configuration; provider-constructor failure; public error redaction; and an existing SQLite schema upgraded through the supported compatibility path.
2. Validate provider names (`mock`, `openrouter`, `local`) and expose complete, accurate AI status including local-model configuration without leaking credentials.
3. Construct providers inside the generation error boundary. Any initialization, timeout, malformed response, or provider error must move the round to a recoverable failed state instead of leaving it stuck in `generating`.
4. Persist `provider_used` from the provider instance that actually generated each SVG. Preserve safe behavior for historical null records and update it on retries.
5. Read OpenRouter/local-model responses through a byte-bounded transport path before JSON parsing and SVG sanitization. Preserve existing timeouts and reject oversized/malformed bodies with the same recoverable public failure semantics.
6. Do not log original prompts or persist/broadcast raw provider exception text. Log actionable server-side context with safe exception classification; return/store a stable user-facing failure message.
7. Keep the Alembic migration chain linear and validate upgrade/downgrade. Ensure the existing local SQLite startup compatibility policy handles `provider_used` without silently diverging from the ORM.
8. Run focused tests and the complete backend test suite.

