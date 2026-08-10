import { apiFetch } from "./client";
import type { GuessResult, Round } from "../types/game";

export function createRound(gameId: string, prompt: string): Promise<Round> {
  return apiFetch<Round>(`/games/${gameId}/rounds`, {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });
}

export function getRound(roundId: string): Promise<Round> {
  return apiFetch<Round>(`/rounds/${roundId}`);
}

export function retryGeneration(roundId: string): Promise<Round> {
  return apiFetch<Round>(`/rounds/${roundId}/retry-generation`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function submitGuess(roundId: string, guessText: string, clueCountUsed: number): Promise<GuessResult> {
  return apiFetch<GuessResult>(`/rounds/${roundId}/guess`, {
    method: "POST",
    body: JSON.stringify({ guess_text: guessText, clue_count_used: clueCountUsed }),
  });
}
