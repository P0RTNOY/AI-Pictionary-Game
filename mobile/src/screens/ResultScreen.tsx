import * as Clipboard from "expo-clipboard";
import { useEffect, useState } from "react";
import { Alert, ScrollView, Text, View } from "react-native";
import { ClipboardCopy, PenLine } from "lucide-react-native";
import { PrimaryButton, SecondaryButton } from "../components/Buttons";
import { ResultLine, TagBlock } from "../components/ResultBlocks";
import { colors, styles } from "../styles";
import type { GameStats, Round } from "../types/game";
import { successHaptic } from "../utils/haptics";
import { artifactProvider, isMockArtifact } from "../utils/providerProvenance";

export function ResultScreen({
  round,
  canCreateNext,
  onNext,
  stats,
  userId,
}: {
  round: Round;
  canCreateNext: boolean;
  onNext: () => void;
  stats?: GameStats | null;
  userId?: string;
}) {
  const [displayScore, setDisplayScore] = useState(0);

  useEffect(() => {
    if (!round.guess) return;
    setDisplayScore(0);
    const target = round.guess.score;
    const step = Math.max(1, Math.ceil(target / 18));
    const interval = setInterval(() => {
      setDisplayScore((current) => {
        const next = Math.min(target, current + step);
        if (next >= target) clearInterval(interval);
        return next;
      });
    }, 24);
    return () => clearInterval(interval);
  }, [round.guess?.score]);

  if (!round.guess) {
    return (
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.sectionTitle}>No result yet</Text>
      </ScrollView>
    );
  }

  async function copyResult() {
    if (!round.guess) return;
    await Clipboard.setStringAsync(
      `AI Pictionary result: ${round.guess.score}/100 (${scoreLabel(round.guess.score)}). Prompt: "${round.original_prompt}". Guess: "${round.guess.guess_text}". Clues: ${round.guess.clue_count_used}.`,
    );
    successHaptic();
    Alert.alert("Copied", "Result summary copied.");
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
      <View style={styles.scorePanel}>
        <Text style={styles.scoreNumber}>{displayScore}</Text>
        <Text style={styles.scoreLabel}>{scoreLabel(round.guess.score)}</Text>
        <Text style={styles.feedback}>{round.guess.short_feedback}</Text>
      </View>
      {stats && userId && (
        <View style={styles.statGrid}>
          <View style={styles.statCell}>
            <Text style={styles.label}>Total</Text>
            <Text style={styles.statValue}>{stats.total_score_by_user[userId] ?? 0}</Text>
          </View>
          <View style={styles.statCell}>
            <Text style={styles.label}>Rounds</Text>
            <Text style={styles.statValue}>{stats.rounds_played}</Text>
          </View>
          <View style={styles.statCell}>
            <Text style={styles.label}>Best</Text>
            <Text style={styles.statValue}>{stats.best_score ?? "-"}</Text>
          </View>
        </View>
      )}
      <ResultLine label="Original" value={round.original_prompt} />
      <ResultLine label="Guess" value={round.guess.guess_text} />
      <ResultLine label="Clues used" value={`${round.guess.clue_count_used} clue${round.guess.clue_count_used === 1 ? "" : "s"} / -${round.guess.clue_penalty} points`} />
      <View style={styles.resultLine}>
        <Text style={styles.label}>Component scores</Text>
        {Object.entries(round.guess.component_scores).map(([key, value]) => (
          <View key={key} style={styles.scoreRow}>
            <Text style={styles.resultText}>{key}</Text>
            <Text style={styles.resultText}>{value}</Text>
          </View>
        ))}
      </View>
      <TagBlock title="Matched" tags={round.guess.matched_parts} empty="No key parts matched yet." tone="mint" />
      <TagBlock title="Missed" tags={round.guess.missed_parts} empty="Nothing major missed." tone="coral" />
      <SecondaryButton label="Copy result" icon={<ClipboardCopy size={18} color={colors.ink} />} onPress={copyResult} />
      {canCreateNext && <PrimaryButton label="Next prompt" icon={<PenLine size={20} color={colors.paper} />} onPress={onNext} />}
    </ScrollView>
  );
}

function scoreLabel(score: number) {
  if (score >= 90) return "Perfect read";
  if (score >= 75) return "Close guess";
  if (score >= 50) return "Getting warm";
  return "Wild guess";
}
