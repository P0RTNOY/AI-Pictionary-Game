import { apiFetch } from "./client";

export type TestNotificationResponse = {
  user_id: string;
  queued: boolean;
  active_device_tokens: number;
  provider: string;
};

export function sendTestNotification(userId: string, gameId?: string | null): Promise<TestNotificationResponse> {
  return apiFetch<TestNotificationResponse>("/debug/send-test-notification", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, game_id: gameId ?? null }),
  });
}
