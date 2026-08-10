import { ScrollView, Text, View } from "react-native";
import { Home, RefreshCw } from "lucide-react-native";
import { PrimaryButton, SecondaryButton } from "../components/Buttons";
import { colors, styles } from "../styles";
import type { Game } from "../types/game";

export function GamePendingScreen({
  game,
  loading,
  error,
  onRetry,
  onHome,
  errorTitle,
}: {
  game: Game | null;
  loading?: boolean;
  error?: string | null;
  onRetry: () => void;
  onHome: () => void;
  errorTitle?: string;
}) {
  return (
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.panel}>
        <Text style={styles.sectionTitle}>{error ? errorTitle || "Could not open game" : "Waiting for first prompt"}</Text>
        <Text style={styles.mutedText}>
          {error
            ? error
            : game?.opponent
              ? `${game.opponent.display_name} needs to create the first prompt. Pull to refresh or wait for realtime updates.`
              : "The game is joined, but no round exists yet."}
        </Text>
        <View style={styles.row}>
          <View style={styles.rowFill}>
            <PrimaryButton label={loading ? "Refreshing" : "Retry"} icon={<RefreshCw size={20} color={colors.paper} />} onPress={onRetry} loading={loading} />
          </View>
          <SecondaryButton label="Home" icon={<Home size={18} color={colors.ink} />} onPress={onHome} />
        </View>
      </View>
    </ScrollView>
  );
}
