import { apiFetch } from "./client";

export type WebSocketTicket = {
  ticket: string;
  expires_at: string;
};

export function createWebSocketTicket(gameId: string): Promise<WebSocketTicket> {
  return apiFetch<WebSocketTicket>(`/games/${encodeURIComponent(gameId)}/websocket-ticket`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}
