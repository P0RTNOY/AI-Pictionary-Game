import { Platform } from "react-native";
import { apiFetch } from "./client";

export function registerDeviceToken(token: string) {
  return apiFetch("/device-tokens", {
    method: "POST",
    body: JSON.stringify({ token, provider: "expo", platform: Platform.OS }),
  });
}
