import { Text, View } from "react-native";
import type { Game, RoundStatus } from "../types/game";
import { styles } from "../styles";

export function StatusPill({ status }: { status: RoundStatus | "your_turn" | "waiting" }) {
  const label =
    status === "your_turn"
      ? "Your turn"
      : status === "waiting"
        ? "Waiting"
        : status === "ready_to_guess"
          ? "Guess"
          : status === "generating"
            ? "Drawing"
            : status === "guessed"
              ? "Scored"
              : "Failed";
  return (
    <View style={[styles.statusPill, (status === "ready_to_guess" || status === "your_turn") && styles.statusReady]}>
      <Text style={styles.statusText}>{label}</Text>
    </View>
  );
}

export function statusForGame(game: Game, userId: string): RoundStatus | "your_turn" | "waiting" {
  const latest = game.latest_round;
  if (!latest || latest.status === "guessed") {
    return game.current_turn_user_id === userId ? "your_turn" : "waiting";
  }
  if (latest.status === "ready_to_guess" && latest.guesser_user_id === userId) {
    return "ready_to_guess";
  }
  return latest.status === "ready_to_guess" ? "waiting" : latest.status;
}
