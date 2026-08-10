import Constants from "expo-constants";
import { assertReleaseApiUrl } from "./apiUrlSafety";

export const DEFAULT_API_URL = "http://localhost:8000";

export const APP_ENV = process.env.EXPO_PUBLIC_APP_ENV ?? Constants.expoConfig?.extra?.appEnv ?? "local";
export const BUILD_PROFILE = process.env.EXPO_PUBLIC_BUILD_PROFILE ?? Constants.expoConfig?.extra?.buildProfile ?? "local";
const configuredApiUrl = process.env.EXPO_PUBLIC_API_URL ?? Constants.expoConfig?.extra?.apiUrl ?? DEFAULT_API_URL;
const runtimeIsDevelopment = typeof __DEV__ !== "undefined" && __DEV__;
export const API_URL = assertReleaseApiUrl(configuredApiUrl, runtimeIsDevelopment);
export const APP_VERSION = Constants.expoConfig?.version ?? "0.1.0";

export function appDiagnostics() {
  return {
    appName: Constants.expoConfig?.name ?? "AI Pictionary",
    appVersion: APP_VERSION,
    appEnv: APP_ENV,
    buildProfile: BUILD_PROFILE,
    apiUrl: API_URL,
    scheme: Constants.expoConfig?.scheme ?? "aipictionary",
    runtimeVersion:
      typeof Constants.expoConfig?.runtimeVersion === "string"
        ? Constants.expoConfig.runtimeVersion
        : Constants.expoConfig?.version ?? "appVersion",
  };
}
