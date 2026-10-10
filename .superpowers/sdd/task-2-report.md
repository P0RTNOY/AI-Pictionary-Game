# Task 2 Report: Provider provenance, configuration, and recoverable generation failures

## Status and commit

- Status: complete
- Commit: `690df72d0876573d2618ee61eb81f3b509e909b5`
- Subject: `fix: harden AI provider generation safety`
- Branch: `codex/beta-release-readiness`
- Remote actions: none; the commit was not pushed.

## Implementation

- Restricted configured AI providers to exactly `mock`, `openrouter`, and `local`. Any other value raises `AIConfigurationError("Unsupported AI provider configuration")` instead of silently selecting mock.
- Completed the `/ai/status` response contract with `local_model_configured`, requiring both local-model URL and model name while returning neither value.
- Made `provider_used` nullable for historical and not-yet-attempted rows. New rounds start with null provenance; each actual attempt records the instantiated provider's `name`; retryable rows clear stale provenance and are updated by the retry's provider.
- Moved provider construction inside the database-backed generation recovery boundary. Constructor failure now marks every pending/generating SVG failed, increments pending attempts, marks the round failed, and emits retry-compatible failure events.
- Standardized public failures as:
  - code: `generation_failed`
  - message: `Drawing generation failed. Please try again.`
- Removed original prompt values from generation/create/retry logs and removed raw exception strings from stored SVG errors and event payloads. Server logs retain only safe IDs, provider/tier metadata, and the qualified exception class.
- Added reusable async and sync bounded JSON transport helpers. They preserve existing finite provider timeouts, reject oversized declared `Content-Length`, stop streamed accumulation before crossing the configurable `AI_PROVIDER_RESPONSE_MAX_BYTES` ceiling (default `1,000,000` bytes), parse only after the bound is enforced, and validate provider message shapes.
- Routed OpenRouter SVG generation, OpenRouter async/sync judging, and local-model SVG generation through the bounded path.
- Added nullable `provider_used` Alembic revision `3ada93e0ae67`, kept the chain linear from `20260701_0001`, and extended the repository's SQLite light-migration compatibility path in `app/db.py` (the repository has no `app/database.py`).
- Added focused tests without network access. Provider HTTP behavior uses `httpx.MockTransport`; migration checks use disposable SQLite files.
- Added no dependency.

## TDD evidence

### RED

Command:

```text
cd /Users/portnoy/Documents/MobileGame/backend
./.venv/bin/pytest -q tests/test_ai_provider_safety.py
```

Recorded output summary (verbatim):

```text
FFFFFFFFFFF                                                              [100%]
=================================== FAILURES ===================================
FAILED tests/test_ai_provider_safety.py::test_generation_persists_provenance_from_actual_provider
FAILED tests/test_ai_provider_safety.py::test_retry_replaces_provenance_only_for_retried_sketches
FAILED tests/test_ai_provider_safety.py::test_unknown_provider_raises_stable_configuration_error
FAILED tests/test_ai_provider_safety.py::test_provider_constructor_failure_finalizes_round_for_retry
FAILED tests/test_ai_provider_safety.py::test_provider_failures_redact_prompts_and_exception_details
FAILED tests/test_ai_provider_safety.py::test_bounded_json_rejects_oversized_declared_response
FAILED tests/test_ai_provider_safety.py::test_bounded_json_rejects_oversized_streamed_response
FAILED tests/test_ai_provider_safety.py::test_local_provider_rejects_malformed_response_shape
FAILED tests/test_ai_provider_safety.py::test_ai_status_schema_includes_complete_local_configuration
FAILED tests/test_ai_provider_safety.py::test_sqlite_light_migration_adds_nullable_provider_used
FAILED tests/test_ai_provider_safety.py::test_provider_used_alembic_migration_is_nullable_and_reversible
11 failed in 1.00s
```

The failures were for the intended missing behaviors: pending rows contained configured `mock`; retry provenance stayed `mock`; configuration/response exception classes and bounded helper did not exist; constructor errors escaped; raw provider errors were public; `local_model_configured` was absent from the response model; the light migration did not accept a disposable engine or add the column; and the Alembic column was non-null.

### GREEN: focused Task 2 tests

Command:

```text
cd /Users/portnoy/Documents/MobileGame/backend
./.venv/bin/pytest -q tests/test_ai_provider_safety.py
```

Output:

```text
...........                                                              [100%]
11 passed in 0.74s
```

### Existing focused regression tests

Command:

```text
cd /Users/portnoy/Documents/MobileGame/backend
./.venv/bin/pytest -q tests/test_game_flow.py tests/test_infra.py
```

Output:

```text
........................                                                 [100%]
24 passed in 1.03s
```

### Complete backend suite in the working tree

Command:

```text
cd /Users/portnoy/Documents/MobileGame/backend
./.venv/bin/pytest -q
```

Output:

```text
.......................................                                  [100%]
39 passed in 1.61s
```

This run included two valuable but unrelated reset/debug WIP tests that were intentionally not staged.

### Exact selectively staged tree

The index was archived to a disposable directory and tested before commit so unstaged WIP could not affect the result.

Command:

```text
task2_index_tree=$(git write-tree)
task2_verify_dir=$(mktemp -d)
git archive "$task2_index_tree" | tar -x -C "$task2_verify_dir"
cd "$task2_verify_dir/backend"
/Users/portnoy/Documents/MobileGame/backend/.venv/bin/pytest -q
```

Output:

```text
.....................................                                    [100%]
37 passed in 4.49s
verified staged tree: 8ab14402c7df18012746904f9c4f8897543fe44b
```

### Post-commit tree

Command:

```text
git archive 690df72d0876573d2618ee61eb81f3b509e909b5 | tar -x -C "$task2_postcommit_dir"
cd "$task2_postcommit_dir/backend"
/Users/portnoy/Documents/MobileGame/backend/.venv/bin/pytest -q
```

Output:

```text
.....................................                                    [100%]
37 passed in 1.53s
```

## Migration checks

### Focused pytest upgrade/downgrade coverage

The focused suite creates disposable legacy and Alembic-managed SQLite databases. It verifies:

- light migration adds nullable `provider_used` to an existing `generated_svgs` table;
- initial revision does not contain the column;
- upgrade to head adds it as nullable;
- downgrade to `20260701_0001` removes it.

These checks are included in the 11/11 focused and 37/37 committed-tree results above.

### Supported Alembic commands and disposable inspection

Commands:

```text
DATABASE_URL="sqlite:///$task2_db_path" ./.venv/bin/alembic heads
DATABASE_URL="sqlite:///$task2_db_path" ./.venv/bin/alembic upgrade head
DATABASE_URL="sqlite:///$task2_db_path" ./.venv/bin/alembic current
DATABASE_URL="sqlite:///$task2_db_path" ./.venv/bin/alembic downgrade 20260701_0001
# inspect with sqlite3: provider_used absent
DATABASE_URL="sqlite:///$task2_db_path" ./.venv/bin/alembic upgrade head
# inspect with sqlite3: provider_used present and nullable
```

Output:

```text
3ada93e0ae67 (head)
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 20260701_0001, initial schema
INFO  [alembic.runtime.migration] Running upgrade 20260701_0001 -> 3ada93e0ae67, Add nullable provider_used provenance to generated SVGs.
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
3ada93e0ae67 (head)
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade 3ada93e0ae67 -> 20260701_0001, Add nullable provider_used provenance to generated SVGs.
downgrade check: provider_used absent
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade 20260701_0001 -> 3ada93e0ae67, Add nullable provider_used provenance to generated SVGs.
upgrade check: provider_used present and nullable
```

Post-commit, a fresh archived commit tree was also upgraded to head, reported `3ada93e0ae67 (head)`, downgraded to `20260701_0001`, and confirmed `provider_used` absent.

## Files committed

- `backend/alembic/versions/3ada93e0ae67_add_provider_used_to_generatedsvg.py`
- `backend/app/ai.py`
- `backend/app/db.py`
- `backend/app/models.py`
- `backend/app/orm_models.py`
- `backend/app/services.py`
- `backend/tests/test_ai_provider_safety.py`

## Scope and self-review

- Inspected `git diff --cached --check`: passed.
- Inspected the complete staged diff and committed file list.
- Confirmed no unmerged paths.
- Confirmed no `.env`, private-key, certificate, or credential-bearing path was staged.
- A staged-diff credential-pattern check found no private-key block or credential-bearing PostgreSQL URL.
- Confirmed `backend/app/main.py`, `backend/tests/test_infra.py`, README/docs, mobile files, mock-art edits in `backend/app/ai.py`, reset helper edits in `backend/app/services.py`, and other unrelated WIP were not committed.
- Confirmed unknown configuration does not silently become mock.
- Confirmed actual provider provenance is instance-derived on both first attempts and retries.
- Confirmed provider construction is inside the recoverable DB boundary.
- Confirmed raw prompt/exception values are not logged, stored, or broadcast by generation paths.
- Confirmed response size is checked both from declared length and during streaming before JSON parsing or SVG sanitization.
- Confirmed historical null provenance is schema-safe and the migration remains focused on one nullable column.
- Confirmed no session/auth schema or deploy-environment startup policy was added.

## Concerns and unverified behavior

- No live OpenRouter or local-model call was made, as required. Transport behavior is verified with in-memory HTTPX transports rather than a live upstream.
- Alembic upgrade/downgrade was exercised on disposable SQLite databases. PostgreSQL-specific migration execution was not available in this task environment; the migration uses a standard nullable `add_column`/`drop_column` pair.
- The repository does not define a separate lint, formatter, type-check, or build command for the Python backend; pytest and Alembic commands were the supported validation used.
- Unrelated pre-existing working-tree changes remain intentionally uncommitted and were not pushed.

## Review amendment: preserve completed art after retry constructor failure

### Finding and fix

Review found that `finalize_provider_initialization_failure` always marked a round failed and emitted `available_svgs: 0`. During a partial retry, that discarded the usability of already-completed art even though completed SVG content and provenance still existed.

The amendment now counts surviving `done` SVG rows after safely failing only pending/generating rows. A nonzero count restores `ready_to_guess` and emits `round.ready_to_guess` with the accurate count; zero completed rows retain the original `failed`/`round.failed` behavior. The regression also proves completed content, provenance, and attempt count remain unchanged while retryable rows receive the stable public error, null provenance, and incremented attempt count.

### Amendment RED

Command:

```text
cd /Users/portnoy/Documents/MobileGame/backend
./.venv/bin/pytest -q tests/test_ai_provider_safety.py::test_provider_constructor_failure_preserves_partial_retry_success
```

Output (verbatim):

```text
F                                                                        [100%]
=================================== FAILURES ===================================
______ test_provider_constructor_failure_preserves_partial_retry_success _______
>       assert generated.status == RoundStatus.ready_to_guess
E       AssertionError: assert <RoundStatus.failed: 'failed'> == <RoundStatus....ady_to_guess'>
E
E         - ready_to_guess
E         + failed
tests/test_ai_provider_safety.py:143: AssertionError
------------------------------ Captured log call -------------------------------
WARNING  ai_pictionary.services:services.py:293 generation.provider_initialization_failed
=========================== short test summary info ============================
FAILED tests/test_ai_provider_safety.py::test_provider_constructor_failure_preserves_partial_retry_success
1 failed in 0.69s
```

### Amendment GREEN: regression and focused Task 2 file

Commands:

```text
cd /Users/portnoy/Documents/MobileGame/backend
./.venv/bin/pytest -q tests/test_ai_provider_safety.py::test_provider_constructor_failure_preserves_partial_retry_success
./.venv/bin/pytest -q tests/test_ai_provider_safety.py
```

Output:

```text
.                                                                        [100%]
1 passed in 0.59s
............                                                             [100%]
12 passed in 0.80s
```

The second command includes and passes the original all-zero constructor-failure regression.

### Amendment GREEN: full working-tree backend suite

Command:

```text
cd /Users/portnoy/Documents/MobileGame/backend
./.venv/bin/pytest -q
```

Output:

```text
........................................                                 [100%]
40 passed in 1.43s
```

### Amendment GREEN: exact selectively staged tree

Commands:

```text
task2_fix_tree=$(git write-tree)
task2_fix_verify_dir=$(mktemp -d)
git archive "$task2_fix_tree" | tar -x -C "$task2_fix_verify_dir"
cd "$task2_fix_verify_dir/backend"
/Users/portnoy/Documents/MobileGame/backend/.venv/bin/pytest -q tests/test_ai_provider_safety.py
/Users/portnoy/Documents/MobileGame/backend/.venv/bin/pytest -q
```

Output:

```text
............                                                             [100%]
12 passed in 0.71s
......................................                                   [100%]
38 passed in 1.48s
verified amendment tree: 27bbddd37f36636968a22f78ed74c1eca2d7317e
```

The working-tree/full-suite count remains two tests higher because unrelated reset/debug WIP is intentionally unstaged. The exact staged tree verifies the amendment independently.

### Amendment commit and post-commit verification

- Commit: `ab145a688ed52df85ac2ed40c12206d0cce3bc4e`
- Subject: `fix: preserve completed art after retry failure`
- Files: `backend/app/services.py`, `backend/tests/test_ai_provider_safety.py`
- Push: none

Commands:

```text
git archive ab145a688ed52df85ac2ed40c12206d0cce3bc4e | tar -x -C "$task2_fix_post_dir"
cd "$task2_fix_post_dir/backend"
/Users/portnoy/Documents/MobileGame/backend/.venv/bin/pytest -q tests/test_ai_provider_safety.py
/Users/portnoy/Documents/MobileGame/backend/.venv/bin/pytest -q
```

Output:

```text
............                                                             [100%]
12 passed in 9.47s
......................................                                   [100%]
38 passed in 3.23s
verified commit: ab145a688ed52df85ac2ed40c12206d0cce3bc4e
```
