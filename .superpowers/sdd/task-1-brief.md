### Task 1: Repository hygiene, Expo compatibility, and build configuration

**Files:**
- Modify: `.gitignore`
- Modify: `mobile/package.json`
- Modify: `mobile/package-lock.json`
- Modify: `mobile/app.json` or introduce the smallest existing-convention Expo config module if runtime validation requires it
- Modify: `mobile/eas.json`
- Verify: `mobile/ios/AIPictionary/Images.xcassets/**`
- Verify: `mobile/assets/**`

**Requirements:**

1. Ignore `graphify-out/` and `.superpowers/sdd/` as generated/scratch output. Remove only the locally generated `graphify-out/` directory after validating it is the exact non-symlink repository child; do not remove source or user data.
2. Run `npx expo install --fix` from `mobile` so Expo SDK 54 dependencies are resolved by Expo's supported workflow. Review every manifest/lockfile change.
3. Remove the `appConfigFieldsNotSyncedCheck` suppression. Resolve any resulting Expo Doctor issue through configuration or native asset consistency, not by disabling the check.
4. Ensure iOS, Android, and web icon/splash configuration points to real, correctly sized branded artwork. Do not ship the blank legacy iOS icon or a featureless splash square as the visible logo. Preserve good artwork and make native/configured assets consistent.
5. Make staging and production configuration reject a missing or loopback `EXPO_PUBLIC_API_URL`; local development may retain a documented loopback default. Keep public configuration out of secret storage and document how EAS receives the value.
6. Run `npm run typecheck`, `npx expo-doctor`, and an Expo config export/bundle smoke check supported by the installed toolchain.

