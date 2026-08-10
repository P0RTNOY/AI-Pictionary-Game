import { apiFetch } from "./client";
import type { Game, GameEvent, GameStats } from "../types/game";

export function createGame(player1Id: string, player2Id: string): Promise<Game> {
  return apiFetch<Game>("/games", {
    method: "POST",
    body: JSON.stringify({ player_1_id: player1Id, player_2_id: player2Id }),
  });
}

export function listGames(userId: string): Promise<Game[]> {
  return apiFetch<Game[]>(`/users/${userId}/games`);
}

export function getGame(gameId: string): Promise<Game> {
  return apiFetch<Game>(`/games/${gameId}`);
}

export function listEvents(gameId: string, afterId = 0): Promise<GameEvent[]> {
  return apiFetch<GameEvent[]>(`/games/${gameId}/events?after_id=${afterId}`);
}

export function getGameStats(gameId: string): Promise<GameStats> {
  return apiFetch<GameStats>(`/games/${gameId}/stats`);
}
