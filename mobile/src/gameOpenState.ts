export type GameOpenState = {
  pendingGameId: string | null;
  openingGameId: string | null;
};

export type GameOpenRetirementMode = "preserve-pending" | "clear-pending";

export function retireGameOpenState(state: GameOpenState, mode: GameOpenRetirementMode): GameOpenState {
  return {
    pendingGameId: mode === "preserve-pending" ? state.pendingGameId ?? state.openingGameId : null,
    openingGameId: null,
  };
}
