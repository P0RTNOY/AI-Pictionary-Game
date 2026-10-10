# Task 1 Report: Repository Hygiene, Expo Compatibility, and Build Configuration

## Status

Completed and committed as `df98a8e build: stabilize Expo beta configuration` on `codex/beta-release-readiness`.

## Implementation

- Added `graphify-out/` and `.superpowers/sdd/` to `.gitignore`.
- Validated `graphify-out` resolved exactly to the normal repository child, had no symlinks, enumerated it, then moved only that generated directory to the local Trash (recoverable removal).
- Ran Expo's supported resolver, `npx expo install --fix`, which updated Expo to `~54.0.36`, removed the redundant direct `@expo/metro-config` dependency, and synchronized the lockfile. It retained/added Expo-compatible web and font dependencies required by the app configuration.
- Removed the `appConfigFieldsNotSyncedCheck` suppression.
- Added `mobile/app.config.js`, derived from static `app.json`, to supply a local loopback default only outside release environments and reject missing, malformed, non-HTTP(S), loopback, or unspecified `EXPO_PUBLIC_API_URL` values for staging and production.
- Added EAS `development`, `preview`, and `production` environment selection and documented that preview/production API URLs are plaintext EAS environment values, not secrets.
- Updated runtime API configuration to read the validated public app-config value.
- Configured iOS, Android, and web Expo branding with the 1024x1024 v2 icon. Copied that inspected branded artwork into the native iOS AppIcon and splash image set, and preserved the native splash storyboard's centered logo/background wiring. The blank legacy iOS icon remains unused.
- Added the beta-release-readiness plan document to the commit as requested.

## Commands and Results

| Command | Result |
| --- | --- |
| `npx expo install --fix` (from `mobile`) | Passed. Expo updated from `~54.0.0` to `~54.0.36`; dependencies and lockfile reconciled. npm reported 26 audit findings, none changed by this task. |
| `npm run typecheck` (from `mobile`) | Passed. |
| `npx expo config --type public --json` (from `mobile`) | Passed. Confirmed configured icon, splash, and Android adaptive-icon paths. |
| Direct dynamic-config checks with staging/production missing or loopback values | Passed. Missing, `localhost`, `127.0.0.2`, `[::1]`, and `0.0.0.0` were rejected; HTTPS was accepted. |
| Asset/config consistency check (`cmp`, `sips`, configured-path assertions) | Passed. Expo configured assets and native AppIcon/splash assets match and are 1024x1024. |
| `npx expo export --platform web --output-dir <temporary directory>` | Passed. Metro bundled 2,242 modules and produced `index.html`, metadata, and the web bundle. |
| `npx expo-doctor` (from `mobile`) | Completed with 17/18 checks passing. The sole failure is the intentional hybrid native-workflow warning described below. |
| `git diff --cached --check` | Passed before commit. |

## Files Committed

- `.gitignore`
- `docs/superpowers/plans/2026-08-10-beta-release-readiness.md`
- `mobile/.env.example`
- `mobile/app.config.js`
- `mobile/app.json`
- `mobile/assets/app-icon-v2.png`
- `mobile/eas.json`
- `mobile/ios/AIPictionary/Images.xcassets/AppIcon.appiconset/App-Icon-1024x1024-v2.png`
- `mobile/ios/AIPictionary/Images.xcassets/AppIcon.appiconset/Contents.json`
- `mobile/ios/AIPictionary/Images.xcassets/SplashScreenLogo.imageset/Contents.json`
- `mobile/ios/AIPictionary/Images.xcassets/SplashScreenLogo.imageset/splash-logo-v2.png`
- `mobile/ios/AIPictionary/SplashScreen.storyboard`
- `mobile/package.json`
- `mobile/package-lock.json`
- `mobile/src/config.ts`

## Self-review

- Reviewed the complete staged file list, textual diff, lockfile root dependency changes, binary asset dimensions, and native asset references before committing.
- Confirmed the staged scope excluded all backend and mobile screen/API WIP, all environment values, and the ignored `.superpowers/sdd` report directory.
- Confirmed no remote action was performed. The unrelated working-tree changes remain untouched.

## Concern / Remaining Validation

`expo-doctor` cannot pass its final `appConfigFieldsNotSyncedCheck` in this intentional hybrid repository: committed `mobile/ios/` scaffolding coexists with Expo native configuration used for managed Android/web. The suppression was removed as required. Passing the check would require either restoring the forbidden suppression, deleting/untracking the committed iOS project for CNG, or removing Android/iOS/native configuration from Expo config and hand-maintaining generated native projects. The beta plan explicitly preserves the iOS scaffolding and branded native assets, so this structural warning is retained and documented rather than hidden. All other Doctor checks pass and the exported config/native assets are explicitly verified consistent.

## Follow-up: URL Guard and EAS CNG Archive Fix

Completed and committed as `03878d2 fix: harden Expo release URL validation`.

### Root Cause and Fix

The original release guard compared IPv6 text forms directly. Node's URL parser canonicalizes both `http://[::ffff:127.0.0.1]:8000` and `http://[::ffff:7f00:1]:8000` to `::ffff:7f00:1`, which did not match either the IPv4 `127/8` expression or the `::1` check. A new deterministic Node test at `mobile/scripts/test-app-config.js` first failed on that mapped-IPv6 case, then passed after the guard began normalizing IPv4-mapped IPv6 into octets. The final guard rejects all `127/8`, IPv4/IPv6 unspecified, IPv6 loopback, IPv4-mapped loopback/unspecified, malformed, and non-HTTP(S) values while accepting HTTPS.

### EAS CNG Resolution

Added `mobile/.easignore` with all necessary mobile exclusions (`.env`, `.env.*`, `node_modules/`, `.expo/`, output directories, logs) and explicit `/ios/` and `/android/` exclusions. EAS remote archives therefore omit the committed local iOS scaffold and generate native projects from the Expo config. The local scaffold remains committed and untouched.

Added the SDK-matched `expo-splash-screen` dependency and plugin configuration. The config plugin uses the same branded `./assets/app-icon-v2.png`, `#FAF7F0` background, contain mode, and 160-point image width as the intended native splash presentation, so remote CNG can reproduce the branded splash rather than depending on the local storyboard.

### Follow-up Commands and Exact Results

| Command | Result |
| --- | --- |
| `node scripts/test-app-config.js` before the fix | Failed as expected: `AssertionError [ERR_ASSERTION]: Missing expected exception: expected http://[::ffff:127.0.0.1]:8000 to be rejected`. |
| `node scripts/test-app-config.js` after the fix | Passed. Covers missing value, localhost, `127/8`, `0.0.0.0`, `::`, `::1`, dotted/hex IPv4-mapped IPv6 loopback, mapped unspecified, malformed URL, non-HTTP(S), and accepted HTTPS. |
| `EXPO_NO_DOTENV=1 npx expo config --type public --json` | Passed. |
| `EXPO_NO_DOTENV=1 npx expo config --type prebuild --json` plus branding/plugin assertions | Passed. Confirmed icon, splash, adaptive-icon, and `expo-splash-screen` plugin all reference the branded asset and expected background. |
| `npm run typecheck` | Passed. |
| `npx expo-doctor` | Passed: `18/18 checks passed. No issues detected!` `.easignore` is recognized by local Doctor, so the former native-sync warning is no longer emitted. |
| Node `ignore` inspection of `mobile/.easignore` | Passed. Confirmed iOS, Android, `.env`/`.env.*`, `node_modules`, `.expo`, and generated outputs are excluded; `app.json`, `app.config.js`, source, package manifests, and branded asset remain included for remote CNG. |
| `git diff --cached --check` | Passed before commit. |
