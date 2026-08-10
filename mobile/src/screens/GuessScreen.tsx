import { useEffect, useMemo, useRef, useState } from "react";
import { Alert, ScrollView, Text, TextInput, View } from "react-native";
import { AlertTriangle, CheckCircle2, Eye } from "lucide-react-native";
import { SvgXml } from "react-native-svg";
import { submitGuess } from "../api/rounds";
import { PrimaryButton, SecondaryButton } from "../components/Buttons";
import { colors, styles } from "../styles";
import type { GuessResult, Round } from "../types/game";
import { captureMessage } from "../utils/errorReporter";
import { warningHaptic } from "../utils/haptics";
import { artifactProvider, isMockArtifact } from "../utils/providerProvenance";

export function GuessScreen({
  round,
  gameId,
  userId,
  lifecycleEpoch,
  onResult,
}: {
  round: Round;
  gameId: string;
  userId: string;
  lifecycleEpoch: number;
  onResult: (result: GuessResult) => void;
}) {
  const submitInFlight = useRef(false);
  const confirmationOpen = useRef(false);
  const submitController = useRef<AbortController | null>(null);
  const [guess, setGuess] = useState("");
  const [loading, setLoading] = useState(false);
  const [visibleCount, setVisibleCount] = useState(1);
  const readySketches = useMemo(() => round.generated_svgs.filter((svg) => svg.status === "done" && svg.svg_text), [round]);
  const visibleSketches = readySketches.slice(0, visibleCount);

  useEffect(() => {
    submitController.current?.abort();
    submitController.current = null;
    submitInFlight.current = false;
    confirmationOpen.current = false;
    setLoading(false);
    return () => submitController.current?.abort();
  }, [lifecycleEpoch]);

  if (round.game_id && round.game_id !== gameId) {
    return (
      <View style={[styles.content, { justifyContent: "center", alignItems: "center" }]}>
        <AlertTriangle size={48} color={colors.coral} style={{ marginBottom: 16 }} />
        <Text style={styles.gameTitle}>Data Mismatch Error</Text>
        <Text style={styles.mutedText}>
          The displayed round (Game ID: {round.game_id}) does not match the active game (Game ID: {gameId}). Please return to home and try again.
        </Text>
      </View>
    );
  }

  async function submit() {
    if (submitInFlight.current || confirmationOpen.current) return;
    if (guess.trim().length < 2) return;
    if (guess.trim().split(/\s+/).length < 3) {
      confirmationOpen.current = true;
      Alert.alert("Submit short guess?", "Short guesses are allowed, but a little more detail usually scores better.", [
        { text: "Keep editing", style: "cancel", onPress: () => { confirmationOpen.current = false; } },
        { text: "Submit", onPress: () => { confirmationOpen.current = false; void submitConfirmed(); } },
      ], { onDismiss: () => { confirmationOpen.current = false; } });
      return;
    }
    void submitConfirmed();
  }

  async function submitConfirmed() {
    if (submitInFlight.current) return;
    submitInFlight.current = true;
    const controller = new AbortController();
    submitController.current = controller;
    setLoading(true);
    try {
      const result = await submitGuess(round.id, guess.trim(), visibleCount, controller.signal);
      if (controller.signal.aborted) return;
      onResult(result);
    } catch (error) {
      if (!controller.signal.aborted) Alert.alert("Could not score guess", error instanceof Error ? error.message : "Unknown error");
    } finally {
      if (submitController.current === controller) {
        if (!controller.signal.aborted) setLoading(false);
        submitInFlight.current = false;
        submitController.current = null;
      }
    }
  }

  function revealNext() {
    warningHaptic();
    Alert.alert("Reveal another clue?", "Each extra sketch reduces the final score by 8 points.", [
      { text: "Cancel", style: "cancel" },
      { text: "Reveal", onPress: () => setVisibleCount((count) => count + 1) },
    ]);
  }

  const isMock = isMockArtifact(round.generated_svgs);
  const provider = artifactProvider(round.generated_svgs);

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.sectionTitle}>{isMock ? "Mock test art" : "AI-generated clues"}</Text>
      <Text style={styles.mutedText}>The original prompt stays hidden until scoring.</Text>
      {isMock && (
        <View accessible accessibilityLabel="Mock output, testing only" style={[styles.panel, styles.mockWarning]}>
          <Text style={[styles.gameTitle, { color: colors.paper }]}>Mock output — testing only</Text>
          <Text style={[styles.mutedText, { color: colors.paper }]}>
            Mock mode uses prompt-derived labels and placeholder shapes. It verifies game flow, not real drawing quality. Use OpenRouter/local provider to evaluate prompt-to-image quality.
          </Text>
        </View>
      )}
      {!isMock && provider && <Text style={styles.tinyText}>Artifact provider: {provider}</Text>}
      <View style={styles.sketchGrid}>
        {visibleSketches.map((svg, index) => (
          <View key={svg.id} style={styles.sketchCard}>
            <Text style={styles.sketchLabel}>{svg.provider_used === "mock" ? "Mock test sketch" : "Sketch"} {index + 1} · {svg.provider_used ?? "provider not recorded"}</Text>
            {isRenderableSvg(svg.svg_text) ? (
              <SvgXml xml={svg.svg_text ?? ""} width="100%" height={220} />
            ) : (
              <SketchRenderFallback svgId={svg.id} roundId={round.id} />
            )}
          </View>
        ))}
      </View>
      {!readySketches.length && (
        <View style={styles.panel}>
          <Text style={styles.gameTitle}>No sketches ready</Text>
          <Text style={styles.mutedText}>The artists are still drawing or all attempts failed. Pull back to the waiting screen and retry if needed.</Text>
        </View>
      )}
      {visibleCount < readySketches.length && (
        <SecondaryButton label="Show next clue" icon={<Eye size={18} color={colors.ink} />} onPress={revealNext} />
      )}
      {readySketches.length > 1 && (
        <View style={styles.penaltyBox}>
          <Text style={styles.label}>Clue penalty</Text>
          <Text style={styles.mutedText}>{visibleCount === 1 ? "Full score is still possible." : `Current penalty: -${(visibleCount - 1) * 8} points.`}</Text>
        </View>
      )}
      <View style={styles.fieldGroup}>
        <Text style={styles.label}>Your guess</Text>
        <TextInput accessibilityLabel="Your guess" editable={!loading} value={guess} onChangeText={setGuess} style={styles.input} placeholder="giraffe gives dolphin piano lesson" placeholderTextColor={colors.muted} />
        <Text style={styles.mutedText}>{visibleCount > 1 ? "Extra clues reduce the score." : "First clue only keeps the full score."}</Text>
      </View>
      <PrimaryButton
        label="Submit guess"
        icon={<CheckCircle2 size={20} color={colors.paper} />}
        onPress={submit}
        disabled={guess.trim().length < 2}
        loading={loading}
      />
    </ScrollView>
  );
}

function isRenderableSvg(value: string | null) {
  return Boolean(value && value.trim().startsWith("<svg"));
}

function SketchRenderFallback({ svgId, roundId }: { svgId: string; roundId: string }) {
  useEffect(() => {
    captureMessage("SVG render fallback shown", { area: "svg_render", svgId, roundId });
  }, [svgId, roundId]);
  return (
    <View style={styles.sketchError}>
      <AlertTriangle size={24} color={colors.coral} />
      <Text style={styles.mutedText}>This sketch could not render.</Text>
    </View>
  );
}
