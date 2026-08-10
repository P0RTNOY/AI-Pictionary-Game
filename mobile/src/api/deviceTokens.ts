import { Platform } from "react-native";
import { apiFetch } from "./client";

export type DeviceTokenSummary = {
  id: string;
  user_id: string;
  provider: string;
  token_fingerprint: string;
  platform: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export function registerDeviceToken(token: string): Promise<DeviceTokenSummary> {
  return apiFetch<DeviceTokenSummary>("/device-tokens", {
    method: "POST",
    body: JSON.stringify({ token, provider: "expo", platform: Platform.OS }),
  });
}

export function unregisterDeviceToken(token: string): Promise<{ unregistered: boolean }> {
  return apiFetch<{ unregistered: boolean }>("/device-tokens/unregister", {
    method: "POST",
    body: JSON.stringify({ token, provider: "expo" }),
  });
}
