import { apiFetch } from "./client";
import type { GuessResult, Round } from "../types/game";

export function createRound(gameId: string, prompt: string, signal?: AbortSignal): Promise<Round> {
  return apiFetch<Round>(`/games/${gameId}/rounds`, {
    method: "POST",
    body: JSON.stringify({ prompt }),
    signal,
  });
}

export function getRound(roundId: string, signal?: AbortSignal): Promise<Round> {
  return apiFetch<Round>(`/rounds/${roundId}`, { signal });
}

export function retryGeneration(roundId: string, signal?: AbortSignal): Promise<Round> {
  return apiFetch<Round>(`/rounds/${roundId}/retry-generation`, {
    method: "POST",
    body: JSON.stringify({}),
    signal,
  });
}

export function submitGuess(roundId: string, guessText: string, clueCountUsed: number, signal?: AbortSignal): Promise<GuessResult> {
  return apiFetch<GuessResult>(`/rounds/${roundId}/guess`, {
    method: "POST",
    body: JSON.stringify({ guess_text: guessText, clue_count_used: clueCountUsed }),
    signal,
  });
}
