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

export function registerDeviceToken(
  token: string,
  accessToken: string,
  signal?: AbortSignal,
): Promise<DeviceTokenSummary> {
  return apiFetch<DeviceTokenSummary>("/device-tokens", {
    method: "POST",
    body: JSON.stringify({ token, provider: "expo", platform: Platform.OS }),
    signal,
  }, accessToken);
}

export function unregisterDeviceToken(
  token: string,
  accessToken: string,
  signal?: AbortSignal,
): Promise<{ unregistered: boolean }> {
  return apiFetch<{ unregistered: boolean }>("/device-tokens/unregister", {
    method: "POST",
    body: JSON.stringify({ token, provider: "expo" }),
    signal,
  }, accessToken);
}
