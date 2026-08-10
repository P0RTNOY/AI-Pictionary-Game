import { useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Alert, Animated, ScrollView, Text, View } from "react-native";
import { CheckCircle2, RotateCcw } from "lucide-react-native";
import { retryGeneration } from "../api/rounds";
import { PrimaryButton, SecondaryButton } from "../components/Buttons";
import { colors, styles } from "../styles";
import type { Round } from "../types/game";
import { artifactProvider, isMockArtifact } from "../utils/providerProvenance";

export function WaitingScreen({
  round,
  userId,
  lifecycleEpoch,
  onRetry,
  onContinue,
}: {
  round: Round;
  userId: string;
  lifecycleEpoch: number;
  onRetry: (round: Round) => void;
  onContinue: () => void;
}) {
  const pulse = useRef(new Animated.Value(0.65)).current;
  const retryInFlight = useRef(false);
  const retryController = useRef<AbortController | null>(null);
  const [loading, setLoading] = useState(false);
  const readyCount = useMemo(() => round.generated_svgs.filter((svg) => svg.status === "done" && svg.svg_text).length, [round]);
  const allFailed = round.generated_svgs.length > 0 && round.generated_svgs.every((svg) => svg.status === "failed");
  const canContinue = round.status === "ready_to_guess" && readyCount > 0 && round.guesser_user_id === userId;

  useEffect(() => {
    retryController.current?.abort();
    retryController.current = null;
    retryInFlight.current = false;
    setLoading(false);
    return () => retryController.current?.abort();
  }, [lifecycleEpoch]);

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 700, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0.65, duration: 700, useNativeDriver: true }),
      ]),
    );
    animation.start();
    return () => {
      animation.stop();
    };
  }, [pulse]);

  async function retry() {
    if (retryInFlight.current) return;
    retryInFlight.current = true;
    const controller = new AbortController();
    retryController.current = controller;
    setLoading(true);
    try {
      const updated = await retryGeneration(round.id, controller.signal);
      if (controller.signal.aborted) return;
      onRetry(updated);
    } catch (error) {
      if (!controller.signal.aborted) Alert.alert("Could not retry artists", error instanceof Error ? error.message : "Unknown error");
    } finally {
      if (retryController.current === controller) {
        if (!controller.signal.aborted) setLoading(false);
        retryInFlight.current = false;
        retryController.current = null;
      }
    }
  }

  const isMock = isMockArtifact(round.generated_svgs);
  const provider = artifactProvider(round.generated_svgs);

  return (
    <ScrollView contentContainerStyle={styles.content}>
      {isMock && (
        <View accessible accessibilityLabel="Mock output, testing only" style={[styles.panel, styles.mockWarning]}>
          <Text style={[styles.gameTitle, { color: colors.paper }]}>Mock output — testing only</Text>
        </View>
      )}
      {!isMock && provider && <Text style={styles.tinyText}>Artifact provider: {provider}</Text>}
      <Text style={styles.sectionTitle}>
        {round.status === "judging" ? "Scoring guess" : round.status === "ready_to_guess" ? "Ready" : "Artists are drawing"}
      </Text>
      <Text style={styles.mutedText}>
        {round.status === "judging"
          ? "The judge is comparing the submitted guess. This can take a moment."
          : readyCount
            ? `${readyCount} artist${readyCount === 1 ? "" : "s"} ready. You can play with any successful sketch.`
            : "Each artist saves independently, so one slow model will not block the whole round."}
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
              <Text style={styles.tinyText}>Provider: {svg.provider_used ?? "not recorded"}</Text>
            </View>
            {svg.status === "done" ? <CheckCircle2 size={24} color={colors.mint} /> : svg.status === "failed" ? <RotateCcw size={22} color={colors.coral} /> : <ActivityIndicator color={colors.blue} />}
          </View>
        ))}
      </View>
      {canContinue && <PrimaryButton label="Guess now" icon={<CheckCircle2 size={20} color={colors.paper} />} onPress={onContinue} />}
      {allFailed && <SecondaryButton label="Retry artists" icon={<RotateCcw size={18} color={colors.ink} />} onPress={retry} loading={loading} />}
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
