import { apiFetch } from "./client";
import type { Game, GameInvite } from "../types/game";

export function createInvite(creatorUserId: string): Promise<GameInvite> {
  return apiFetch<GameInvite>("/invites", {
    method: "POST",
    body: JSON.stringify({ creator_user_id: creatorUserId }),
  });
}

export function getInvite(code: string): Promise<GameInvite> {
  return apiFetch<GameInvite>(`/invites/${code.toUpperCase()}`);
}

export function joinInvite(code: string, userId: string): Promise<Game> {
  return apiFetch<Game>(`/invites/${code.toUpperCase()}/join`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}
