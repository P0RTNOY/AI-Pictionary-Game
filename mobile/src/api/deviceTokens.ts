import { Platform } from "react-native";
import { apiFetch } from "./client";

export function registerDeviceToken(userId: string, token: string) {
  return apiFetch("/device-tokens", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, token, provider: "expo", platform: Platform.OS }),
  });
}
