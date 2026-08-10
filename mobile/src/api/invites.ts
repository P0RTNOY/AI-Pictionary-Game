import { apiFetch } from "./client";
import type { Game, GameInvite, GameInvitePreview } from "../types/game";

export function createInvite(signal?: AbortSignal): Promise<GameInvite> {
  return apiFetch<GameInvite>("/invites", {
    method: "POST",
    body: JSON.stringify({}),
    signal,
  });
}

export function getInvite(code: string, signal?: AbortSignal): Promise<GameInvitePreview> {
  return apiFetch<GameInvitePreview>("/invites/preview", {
    method: "POST",
    body: JSON.stringify({ code }),
    signal,
  });
}

export function joinInvite(code: string, signal?: AbortSignal): Promise<Game> {
  return apiFetch<Game>("/invites/join", {
    method: "POST",
    body: JSON.stringify({ code }),
    signal,
  });
}
