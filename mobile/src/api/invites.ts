import { apiFetch } from "./client";
import type { Game, GameInvite, GameInvitePreview } from "../types/game";

export function createInvite(): Promise<GameInvite> {
  return apiFetch<GameInvite>("/invites", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getInvite(code: string): Promise<GameInvitePreview> {
  return apiFetch<GameInvitePreview>(`/invites/${encodeURIComponent(code)}`);
}

export function joinInvite(code: string): Promise<Game> {
  return apiFetch<Game>(`/invites/${encodeURIComponent(code)}/join`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}
