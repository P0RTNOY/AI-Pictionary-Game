### Task 8: Final independent review, validation, commits, and publication

**Files:**
- Modify only files required by final review findings
- Finalize: `docs/RELEASE_READINESS.md`

**Requirements:**

1. Run an independent whole-branch review against the branch merge base. Fix and re-review every Critical/Important correctness, security, migration, lifecycle, or release issue.
2. Run final validation: full backend tests; configured lint/type checks; backend startup smoke; Alembic heads/current plus clean upgrade and previous-revision upgrade/downgrade on disposable databases; mobile clean dependency consistency, typecheck, Expo Doctor, Expo config, and bundle/startup smoke; repository `git diff --check`; final secret/generated-file/status inspection.
3. Perform all simulator/two-player/provider/device checks the environment genuinely allows. Record limitations honestly and update the release-readiness evidence with exact final commands/results.
4. Organize all intended changes into focused conventional commits after inspecting staged diffs and excluding `.env`, generated output, credentials, and unrelated files. Preserve existing commit `cd63f3f` in ancestry.
5. Push `codex/beta-release-readiness` to `origin` with upstream tracking, verify the remote branch, and create a pull request to `main` if authenticated GitHub tooling is available and validation is green.
6. Finish with a clean working tree or explicitly identify only intentional ignored local state. Provide the requested comprehensive release report.
