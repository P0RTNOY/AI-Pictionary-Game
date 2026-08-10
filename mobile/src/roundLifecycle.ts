import type { Round } from "./types/game";

export type GameScreen =
  | "onboarding"
  | "home"
  | "profile_setup"
  | "edit_profile"
  | "invites"
  | "create_round"
  | "waiting"
  | "guess"
  | "result"
  | "debug"
  | "startup_error";

type RouteInput = {
  latestRound: Pick<Round, "id" | "status" | "guesser_user_id"> | null;
  currentTurnUserId: string;
  userId: string;
  currentScreen: GameScreen;
  force: boolean;
  observedGuessRoundId: string | null;
};

type RouteDecision = {
  screen: GameScreen;
  observedGuessRoundId: string | null;
};

export function decideGameRoute(input: RouteInput): RouteDecision {
  const { latestRound, currentTurnUserId, userId, currentScreen, force, observedGuessRoundId } = input;
  if (!latestRound) {
    return {
      screen: currentTurnUserId === userId ? "create_round" : force ? "waiting" : currentScreen,
      observedGuessRoundId: null,
    };
  }

  if (latestRound.status === "guessed") {
    if (latestRound.guesser_user_id === userId && observedGuessRoundId === latestRound.id) {
      return { screen: "result", observedGuessRoundId };
    }
    return {
      screen: currentTurnUserId === userId ? "create_round" : force ? "waiting" : currentScreen,
      observedGuessRoundId: null,
    };
  }

  if (latestRound.status === "ready_to_guess" || latestRound.status === "judging") {
    if (latestRound.guesser_user_id === userId) {
      return { screen: "guess", observedGuessRoundId: latestRound.id };
    }
    return { screen: "waiting", observedGuessRoundId: null };
  }

  return { screen: "waiting", observedGuessRoundId: null };
}

export function isGuessInteractionAllowed(status: Round["status"]) {
  return status === "ready_to_guess";
}
