import { useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Alert, Animated, ScrollView, Text, View } from "react-native";
import { CheckCircle2, RotateCcw } from "lucide-react-native";
import { retryGeneration } from "../api/rounds";
import { PrimaryButton, SecondaryButton } from "../components/Buttons";
import { colors, styles } from "../styles";
import type { Round } from "../types/game";

export function WaitingScreen({
  round,
  userId,
  onRetry,
  onContinue,
}: {
  round: Round;
  userId: string;
  onRetry: (round: Round) => void;
  onContinue: () => void;
}) {
  const pulse = useRef(new Animated.Value(0.65)).current;
  const [loading, setLoading] = useState(false);
  const readyCount = useMemo(() => round.generated_svgs.filter((svg) => svg.status === "done" && svg.svg_text).length, [round]);
  const allFailed = round.generated_svgs.length > 0 && round.generated_svgs.every((svg) => svg.status === "failed");
  const canContinue = round.status === "ready_to_guess" && readyCount > 0 && round.guesser_user_id === userId;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 700, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0.65, duration: 700, useNativeDriver: true }),
      ]),
    );
    animation.start();
    return () => animation.stop();
  }, [pulse]);

  async function retry() {
    setLoading(true);
    try {
      const updated = await retryGeneration(round.id);
      onRetry(updated);
    } catch (error) {
      Alert.alert("Could not retry artists", error instanceof Error ? error.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.sectionTitle}>{round.status === "ready_to_guess" ? "Ready" : "Artists are drawing"}</Text>
      <Text style={styles.mutedText}>
        {readyCount ? `${readyCount} artist${readyCount === 1 ? "" : "s"} ready. You can play with any successful sketch.` : "Each artist saves independently, so one slow model will not block the whole round."}
      </Text>
      <View style={styles.panel}>
        {round.generated_svgs.map((svg, index) => (
          <View key={svg.id} style={styles.row}>
            <Animated.View style={[styles.heroIcon, svg.status !== "done" && { opacity: pulse }]}>
              <Text style={styles.gameTitle}>{index + 1}</Text>
            </Animated.View>
            <View style={styles.gameRowMain}>
              <Text style={styles.artistName}>{artistLabel(svg.model_tier)}</Text>
              <Text style={styles.mutedText}>{artistStatus(svg.status, svg.generation_time_seconds, svg.error_message, svg.attempts)}</Text>
            </View>
            {svg.status === "done" ? <CheckCircle2 size={24} color={colors.mint} /> : svg.status === "failed" ? <RotateCcw size={22} color={colors.coral} /> : <ActivityIndicator color={colors.blue} />}
          </View>
        ))}
      </View>
      {canContinue && <PrimaryButton label="Guess now" icon={<CheckCircle2 size={20} color={colors.paper} />} onPress={onContinue} />}
      {allFailed && <SecondaryButton label="Retry artists" icon={<RotateCcw size={18} color={colors.ink} />} onPress={retry} />}
      {loading && <Text style={styles.mutedText}>Restarting the artist queue...</Text>}
    </ScrollView>
  );
}

function artistLabel(tier: string) {
  if (tier === "confusing") return "Confusing Artist";
  if (tier === "balanced") return "Balanced Artist";
  if (tier === "literal") return "Literal Artist";
  return tier;
}

function artistStatus(status: string, seconds: number | null, error: string | null, attempts: number) {
  if (status === "done") return `Finished in ${seconds ?? 0}s`;
  if (status === "failed") return error || "Could not draw this one";
  if (status === "generating") return attempts > 1 ? "Trying a cleaner redraw..." : "Sketching, simplifying, sanitizing...";
  return "Warming up the model...";
}
