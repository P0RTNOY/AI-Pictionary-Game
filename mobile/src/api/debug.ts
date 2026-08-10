import { apiFetch } from "./client";

export type TestNotificationResponse = {
  user_id: string;
  queued: boolean;
  active_device_tokens: number;
  provider: string;
};

export function sendTestNotification(userId: string, gameId?: string | null, signal?: AbortSignal): Promise<TestNotificationResponse> {
  return apiFetch<TestNotificationResponse>("/debug/send-test-notification", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, game_id: gameId ?? null }),
    signal,
  });
}

export function resetBackendData(signal?: AbortSignal): Promise<{ deleted_rows: number; ok: boolean }> {
  return apiFetch<{ deleted_rows: number; ok: boolean }>("/debug/reset-local-data", {
    method: "POST",
    body: JSON.stringify({ confirmation: "RESET LOCAL DATA" }),
    signal,
  });
}
