import { apiFetch } from "./client";
import type { User } from "../types/game";

export function createUser(displayName: string, avatarEmoji = "🙂", avatarColor = "#F5C84C"): Promise<User> {
  return apiFetch<User>("/users", {
    method: "POST",
    body: JSON.stringify({ display_name: displayName, avatar_emoji: avatarEmoji, avatar_color: avatarColor }),
  });
}

export function getUser(userId: string): Promise<User> {
  return apiFetch<User>(`/users/${userId}`);
}

export function updateUser(userId: string, payload: { display_name?: string; avatar_emoji?: string; avatar_color?: string }): Promise<User> {
  return apiFetch<User>(`/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
