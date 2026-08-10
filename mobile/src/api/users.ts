import { apiFetch } from "./client";
import type { User } from "../types/game";

export type UserSession = {
  user: User;
  access_token: string;
  token_type: "bearer";
};

export function createUser(displayName: string, avatarEmoji = "🙂", avatarColor = "#F5C84C", signal?: AbortSignal): Promise<UserSession> {
  return apiFetch<UserSession>("/users", {
    method: "POST",
    body: JSON.stringify({ display_name: displayName, avatar_emoji: avatarEmoji, avatar_color: avatarColor }),
    signal,
  });
}

export function getUser(userId: string, signal?: AbortSignal): Promise<User> {
  return apiFetch<User>(`/users/${userId}`, { signal });
}

export function updateUser(userId: string, payload: { display_name?: string; avatar_emoji?: string; avatar_color?: string }, signal?: AbortSignal): Promise<User> {
  return apiFetch<User>(`/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    signal,
  });
}
