import { apiFetch } from "./client";
import type { Game, GameInvite, GameInvitePreview } from "../types/game";

export function createInvite(): Promise<GameInvite> {
  return apiFetch<GameInvite>("/invites", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getInvite(code: string): Promise<GameInvitePreview> {
  return apiFetch<GameInvitePreview>("/invites/preview", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export function joinInvite(code: string): Promise<Game> {
  return apiFetch<Game>("/invites/join", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}
