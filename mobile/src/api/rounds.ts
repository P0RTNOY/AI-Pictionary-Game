import { apiFetch } from "./client";
import type { GuessResult, Round } from "../types/game";

export function createRound(gameId: string, creatorUserId: string, prompt: string): Promise<Round> {
  return apiFetch<Round>(`/games/${gameId}/rounds`, {
    method: "POST",
    body: JSON.stringify({ creator_user_id: creatorUserId, prompt }),
  });
}

export function getRound(roundId: string, userId?: string): Promise<Round> {
  const query = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
  return apiFetch<Round>(`/rounds/${roundId}${query}`);
}

export function retryGeneration(roundId: string, userId: string): Promise<Round> {
  return apiFetch<Round>(`/rounds/${roundId}/retry-generation`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export function submitGuess(roundId: string, userId: string, guessText: string, clueCountUsed: number): Promise<GuessResult> {
  return apiFetch<GuessResult>(`/rounds/${roundId}/guess`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId, guess_text: guessText, clue_count_used: clueCountUsed }),
  });
}
