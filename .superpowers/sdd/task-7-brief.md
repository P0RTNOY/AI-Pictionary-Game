### Task 7: CI, documentation reconciliation, and release evidence

**Files:**
- Add: `.github/workflows/ci.yml` if no equivalent CI exists
- Modify: `README.md`
- Modify: `docs/BETA_TESTING.md`
- Modify: `docs/RELEASE_CANDIDATE_QA.md`
- Add: `docs/RELEASE_READINESS.md`
- Modify: environment examples/config docs only as implementation requires

**Requirements:**

1. Add a focused CI workflow using the repository's package managers that runs backend tests and migration checks plus mobile install/typecheck/Expo Doctor checks. Do not include secrets or live-provider calls.
2. Reconcile every setup/config/provider/debug/reset/build instruction with the final code. Remove stale `Submitting prompt` guidance and describe separate provider/judge debug rows accurately.
3. Document session-token re-onboarding, API URL requirements, migrations, safe local reset scope, mock provenance warnings, provider setup, and exact local validation commands.
4. Create `docs/RELEASE_READINESS.md` with evidence sections: Passed automatically, Passed locally/simulator, Requires external credentials, Requires physical-device QA, Known non-blocking issues, and Release blockers. Include only results actually executed and leave candidate SHA/remote/PR fields ready for final update.
5. Ensure a new developer can run backend and mobile without relying on hidden local state. Never document or copy credential values.
6. Run documentation searches for removed UI labels and configuration drift, then rerun representative documented commands.

