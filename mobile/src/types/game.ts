export type RoundStatus = "generating" | "ready_to_guess" | "guessed" | "failed";
export type SvgStatus = "pending" | "generating" | "done" | "failed";

export type User = {
  id: string;
  display_name: string;
  avatar_url: string | null;
  avatar_emoji: string;
  avatar_color: string;
  created_at: string;
  updated_at: string;
};

export type GeneratedSvg = {
  id: string;
  model_name: string;
  model_tier: string;
  svg_text: string | null;
  generation_time_seconds: number | null;
  status: SvgStatus;
  error_message: string | null;
  attempts: number;
};

export type GuessResult = {
  round_id: string;
  guess_text: string;
  score: number;
  matched_parts: string[];
  missed_parts: string[];
  short_feedback: string;
  judge_result_json: Record<string, unknown>;
  component_scores: Record<string, number>;
  clue_count_used: number;
  clue_penalty: number;
  created_at: string;
};

export type Round = {
  id: string;
  game_id: string;
  creator_user_id: string;
  guesser_user_id: string;
  original_prompt: string;
  status: RoundStatus;
  generated_svgs: GeneratedSvg[];
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  clue_reveal_count: number;
  guess: GuessResult | null;
};

export type Game = {
  id: string;
  player_1_id: string;
  player_2_id: string;
  current_turn_user_id: string;
  status: "active" | "completed" | "archived";
  created_at: string;
  updated_at: string;
  latest_round: Round | null;
  opponent: User | null;
};

export type GameStats = {
  game_id: string;
  rounds_played: number;
  total_score_by_user: Record<string, number>;
  average_score_by_user: Record<string, number>;
  best_score: number | null;
  current_turn_user_id: string;
  last_activity_at: string;
};

export type GameEvent = {
  id: number;
  game_id: string;
  user_id: string | null;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type GameInvitePreview = {
  code: string;
  creator_user_id: string;
  status: "pending" | "accepted" | "expired";
  expires_at: string;
};

export type GameInvite = GameInvitePreview & {
  game_id: string | null;
  accepted_by_user_id: string | null;
  accepted_at: string | null;
  created_at: string;
  updated_at: string;
};
