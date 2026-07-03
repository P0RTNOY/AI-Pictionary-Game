import { apiFetch } from "./client";

export type AIStatus = {
  runtime_provider: string;
  openrouter_configured: boolean;
  mock_mode_notice?: string | null;
  artist_models: { tier: string; model: string; reasoning_effort?: string | null }[];
  judge_model: string;
};

export function getAIStatus(): Promise<AIStatus> {
  return apiFetch<AIStatus>("/ai/status");
}
