import { StatusBar } from "expo-status-bar";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SvgXml } from "react-native-svg";
import { ArrowLeft, CheckCircle2, Home, PenLine, RefreshCw, Send, Sparkles } from "lucide-react-native";
import { useEffect, useMemo, useState } from "react";

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

type RoundStatus = "generating" | "ready_to_guess" | "guessed" | "failed";
type SvgStatus = "pending" | "done" | "failed";

type GeneratedSvg = {
  id: string;
  model_name: string;
  model_tier: string;
  svg_text: string | null;
  generation_time_seconds: number | null;
  status: SvgStatus;
  error_message: string | null;
};

type GuessResult = {
  round_id: string;
  guess_text: string;
  score: number;
  matched_parts: string[];
  missed_parts: string[];
  short_feedback: string;
  created_at: string;
};

type Round = {
  id: string;
  creator_user_id: string;
  guesser_user_id: string;
  original_prompt: string;
  status: RoundStatus;
  generated_svgs: GeneratedSvg[];
  created_at: string;
  completed_at: string | null;
  guess: GuessResult | null;
};

type Screen = "home" | "create" | "waiting" | "guess" | "result";

const randomPrompts = [
  "a robot making shakshuka for a dragon",
  "a giraffe teaching a dolphin how to play piano",
  "a wizard arguing with a toaster in court",
  "a sleepy astronaut babysitting three moon rocks",
  "a cactus DJ playing music for penguins",
];

export default function App() {
  const [screen, setScreen] = useState<Screen>("home");
  const [round, setRound] = useState<Round | null>(null);
  const [prompt, setPrompt] = useState(randomPrompts[0]);
  const [guess, setGuess] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!round || (round.status !== "generating" && round.status !== "ready_to_guess")) {
      return;
    }
    const interval = setInterval(async () => {
      const latest = await fetchRound(round.id);
      if (!latest) {
        return;
      }
      setRound(latest);
      if (latest.status === "ready_to_guess") {
        setScreen("guess");
      }
      if (latest.status === "guessed") {
        setScreen("result");
      }
    }, 1200);
    return () => clearInterval(interval);
  }, [round?.id, round?.status]);

  const readySketches = useMemo(
    () => round?.generated_svgs.filter((svg) => svg.status === "done" && svg.svg_text) ?? [],
    [round],
  );

  async function createChallenge() {
    if (prompt.trim().length < 6) {
      Alert.alert("Add a clearer prompt", "Write at least a few words so the artists have something to draw.");
      return;
    }
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/rounds`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: prompt.trim() }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const created: Round = await response.json();
      setRound(created);
      setGuess("");
      setScreen("waiting");
    } catch (error) {
      Alert.alert("Could not create challenge", getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  async function submitGuess() {
    if (!round || guess.trim().length < 2) {
      return;
    }
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/rounds/${round.id}/guess`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ guess_text: guess.trim() }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const result: GuessResult = await response.json();
      setRound({ ...round, status: "guessed", guess: result, completed_at: result.created_at });
      setScreen("result");
    } catch (error) {
      Alert.alert("Could not score guess", getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  function resetForNextChallenge() {
    setPrompt(randomPrompts[Math.floor(Math.random() * randomPrompts.length)]);
    setGuess("");
    setRound(null);
    setScreen("create");
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="dark" />
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.shell}>
        <Header screen={screen} onHome={() => setScreen("home")} onBack={() => setScreen(round ? "guess" : "home")} />
        {screen === "home" && (
          <ScrollView contentContainerStyle={styles.content}>
            <View style={styles.hero}>
              <View style={styles.heroIcon}>
                <Sparkles size={30} color={colors.ink} strokeWidth={2.2} />
              </View>
              <Text style={styles.title}>AI Pictionary</Text>
              <Text style={styles.subtitle}>Turn a strange sentence into three AI sketches, then let the other player guess it.</Text>
            </View>

            {round ? (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Open current round"
                onPress={() => setScreen(round.status === "guessed" ? "result" : round.status === "ready_to_guess" ? "guess" : "waiting")}
                style={({ pressed }) => [styles.gameRow, pressed && styles.pressed]}
              >
                <View style={styles.gameRowMain}>
                  <Text style={styles.gameTitle}>Local match</Text>
                  <Text style={styles.gamePrompt} numberOfLines={2}>
                    {round.status === "guessed" ? round.guess?.short_feedback : round.original_prompt}
                  </Text>
                </View>
                <StatusPill status={round.status} />
              </Pressable>
            ) : (
              <View style={styles.emptyPanel}>
                <Text style={styles.emptyTitle}>No active rounds</Text>
                <Text style={styles.mutedText}>Start with one weird situation and the local artists will draw immediately.</Text>
              </View>
            )}

            <PrimaryButton label="Create challenge" icon={<PenLine size={20} color={colors.paper} />} onPress={() => setScreen("create")} />
          </ScrollView>
        )}

        {screen === "create" && (
          <ScrollView contentContainerStyle={styles.content}>
            <Text style={styles.sectionTitle}>New challenge</Text>
            <View style={styles.fieldGroup}>
              <Text style={styles.label}>Situation prompt</Text>
              <TextInput
                accessibilityLabel="Situation prompt"
                multiline
                value={prompt}
                onChangeText={setPrompt}
                style={styles.promptInput}
                textAlignVertical="top"
                placeholder="a robot making shakshuka for a dragon"
                placeholderTextColor={colors.muted}
              />
            </View>
            <View style={styles.row}>
              <SecondaryButton
                label="Random"
                icon={<RefreshCw size={18} color={colors.ink} />}
                onPress={() => setPrompt(randomPrompts[Math.floor(Math.random() * randomPrompts.length)])}
              />
              <View style={styles.rowFill}>
                <PrimaryButton
                  label={loading ? "Sending" : "Generate"}
                  icon={loading ? <ActivityIndicator color={colors.paper} /> : <Send size={19} color={colors.paper} />}
                  onPress={createChallenge}
                  disabled={loading}
                />
              </View>
            </View>
          </ScrollView>
        )}

        {screen === "waiting" && round && (
          <ScrollView contentContainerStyle={styles.content}>
            <Text style={styles.sectionTitle}>Artists are drawing</Text>
            <View style={styles.progressPanel}>
              {round.generated_svgs.map((svg, index) => (
                <View key={svg.id} style={styles.artistRow}>
                  <View style={styles.artistBadge}>
                    <Text style={styles.artistNumber}>{index + 1}</Text>
                  </View>
                  <View style={styles.gameRowMain}>
                    <Text style={styles.artistName}>Sketch {index + 1}</Text>
                    <Text style={styles.mutedText}>{svg.status === "done" ? `${svg.generation_time_seconds ?? 0}s` : svg.status}</Text>
                  </View>
                  {svg.status === "done" ? (
                    <CheckCircle2 size={24} color={colors.mint} />
                  ) : (
                    <ActivityIndicator color={colors.blue} />
                  )}
                </View>
              ))}
            </View>
          </ScrollView>
        )}

        {screen === "guess" && round && (
          <ScrollView contentContainerStyle={styles.content}>
            <Text style={styles.sectionTitle}>Guess the prompt</Text>
            <View style={styles.sketchGrid}>
              {readySketches.map((svg, index) => (
                <View key={svg.id} style={styles.sketchCard}>
                  <Text style={styles.sketchLabel}>Sketch {index + 1}</Text>
                  <SvgXml xml={svg.svg_text ?? ""} width="100%" height={220} />
                </View>
              ))}
            </View>
            <View style={styles.fieldGroup}>
              <Text style={styles.label}>Your guess</Text>
              <TextInput
                accessibilityLabel="Your guess"
                value={guess}
                onChangeText={setGuess}
                style={styles.guessInput}
                placeholder="giraffe gives dolphin piano lesson"
                placeholderTextColor={colors.muted}
              />
            </View>
            <PrimaryButton
              label={loading ? "Scoring" : "Submit guess"}
              icon={loading ? <ActivityIndicator color={colors.paper} /> : <CheckCircle2 size={20} color={colors.paper} />}
              onPress={submitGuess}
              disabled={loading || guess.trim().length < 2}
            />
          </ScrollView>
        )}

        {screen === "result" && round?.guess && (
          <ScrollView contentContainerStyle={styles.content}>
            <View style={styles.scorePanel}>
              <Text style={styles.scoreNumber}>{round.guess.score}</Text>
              <Text style={styles.scoreLabel}>semantic score</Text>
              <Text style={styles.feedback}>{round.guess.short_feedback}</Text>
            </View>
            <ResultLine label="Original" value={round.original_prompt} />
            <ResultLine label="Guess" value={round.guess.guess_text} />
            <TagBlock title="Matched" tags={round.guess.matched_parts} empty="No key parts matched yet." tone="mint" />
            <TagBlock title="Missed" tags={round.guess.missed_parts} empty="Nothing major missed." tone="coral" />
            <PrimaryButton label="Next challenge" icon={<PenLine size={20} color={colors.paper} />} onPress={resetForNextChallenge} />
          </ScrollView>
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Header({ screen, onHome, onBack }: { screen: Screen; onHome: () => void; onBack: () => void }) {
  const showBack = screen !== "home";
  return (
    <View style={styles.header}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={showBack ? "Go back" : "Go home"}
        onPress={showBack ? onBack : onHome}
        style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}
      >
        {showBack ? <ArrowLeft size={23} color={colors.ink} /> : <Home size={22} color={colors.ink} />}
      </Pressable>
      <Text style={styles.headerTitle}>Daily sketch duel</Text>
      <View style={styles.iconButtonSpacer} />
    </View>
  );
}

function PrimaryButton({
  label,
  icon,
  onPress,
  disabled,
}: {
  label: string;
  icon: React.ReactNode;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: Boolean(disabled) }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [styles.primaryButton, disabled && styles.disabled, pressed && styles.pressed]}
    >
      {icon}
      <Text style={styles.primaryButtonText}>{label}</Text>
    </Pressable>
  );
}

function SecondaryButton({ label, icon, onPress }: { label: string; icon: React.ReactNode; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}>
      {icon}
      <Text style={styles.secondaryButtonText}>{label}</Text>
    </Pressable>
  );
}

function StatusPill({ status }: { status: RoundStatus }) {
  const label = status === "ready_to_guess" ? "Your turn" : status === "generating" ? "Drawing" : status === "guessed" ? "Scored" : "Failed";
  return (
    <View style={[styles.statusPill, status === "ready_to_guess" && styles.statusReady]}>
      <Text style={styles.statusText}>{label}</Text>
    </View>
  );
}

function ResultLine({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.resultLine}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.resultText}>{value}</Text>
    </View>
  );
}

function TagBlock({
  title,
  tags,
  empty,
  tone,
}: {
  title: string;
  tags: string[];
  empty: string;
  tone: "mint" | "coral";
}) {
  return (
    <View style={styles.resultLine}>
      <Text style={styles.label}>{title}</Text>
      {tags.length ? (
        <View style={styles.tags}>
          {tags.map((tag) => (
            <View key={tag} style={[styles.tag, tone === "mint" ? styles.tagMint : styles.tagCoral]}>
              <Text style={styles.tagText}>{tag}</Text>
            </View>
          ))}
        </View>
      ) : (
        <Text style={styles.mutedText}>{empty}</Text>
      )}
    </View>
  );
}

async function fetchRound(roundId: string): Promise<Round | null> {
  try {
    const response = await fetch(`${API_URL}/rounds/${roundId}`);
    if (!response.ok) {
      return null;
    }
    return response.json();
  } catch {
    return null;
  }
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Unknown error";
}

const colors = {
  paper: "#FAF7F0",
  surface: "#FFFFFF",
  ink: "#171717",
  muted: "#6B7280",
  line: "#E7E0D3",
  coral: "#FF6B5F",
  mint: "#24A98C",
  gold: "#F5C84C",
  blue: "#4E79FF",
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.paper,
  },
  shell: {
    flex: 1,
  },
  header: {
    minHeight: 60,
    paddingHorizontal: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: "700",
    color: colors.ink,
  },
  iconButton: {
    width: 48,
    height: 48,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
  },
  iconButtonSpacer: {
    width: 48,
    height: 48,
  },
  content: {
    padding: 20,
    gap: 18,
    paddingBottom: 36,
  },
  hero: {
    paddingTop: 12,
    gap: 12,
  },
  heroIcon: {
    width: 58,
    height: 58,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.gold,
    borderWidth: 1,
    borderColor: colors.ink,
  },
  title: {
    fontSize: 34,
    lineHeight: 40,
    fontWeight: "800",
    color: colors.ink,
  },
  subtitle: {
    fontSize: 17,
    lineHeight: 25,
    color: colors.muted,
  },
  sectionTitle: {
    fontSize: 26,
    lineHeight: 32,
    fontWeight: "800",
    color: colors.ink,
  },
  emptyPanel: {
    padding: 18,
    borderRadius: 8,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
    gap: 6,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: "800",
    color: colors.ink,
  },
  mutedText: {
    fontSize: 14,
    lineHeight: 20,
    color: colors.muted,
  },
  gameRow: {
    minHeight: 92,
    padding: 16,
    borderRadius: 8,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  gameRowMain: {
    flex: 1,
    gap: 4,
  },
  gameTitle: {
    fontSize: 18,
    fontWeight: "800",
    color: colors.ink,
  },
  gamePrompt: {
    fontSize: 14,
    lineHeight: 20,
    color: colors.muted,
  },
  statusPill: {
    minHeight: 32,
    paddingHorizontal: 10,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 8,
    backgroundColor: "#EEF2FF",
  },
  statusReady: {
    backgroundColor: "#DDF7EF",
  },
  statusText: {
    fontSize: 12,
    fontWeight: "800",
    color: colors.ink,
  },
  fieldGroup: {
    gap: 8,
  },
  label: {
    fontSize: 13,
    fontWeight: "800",
    textTransform: "uppercase",
    color: colors.muted,
  },
  promptInput: {
    minHeight: 164,
    padding: 16,
    borderRadius: 8,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
    fontSize: 17,
    lineHeight: 24,
    color: colors.ink,
  },
  guessInput: {
    minHeight: 54,
    paddingHorizontal: 16,
    borderRadius: 8,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
    fontSize: 17,
    color: colors.ink,
  },
  row: {
    flexDirection: "row",
    gap: 12,
    alignItems: "center",
  },
  rowFill: {
    flex: 1,
  },
  primaryButton: {
    minHeight: 54,
    borderRadius: 8,
    paddingHorizontal: 18,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 10,
    backgroundColor: colors.ink,
  },
  primaryButtonText: {
    color: colors.paper,
    fontSize: 16,
    fontWeight: "800",
  },
  secondaryButton: {
    minHeight: 54,
    borderRadius: 8,
    paddingHorizontal: 16,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 8,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
  },
  secondaryButtonText: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "800",
  },
  disabled: {
    opacity: 0.45,
  },
  pressed: {
    opacity: 0.72,
  },
  progressPanel: {
    borderRadius: 8,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
  },
  artistRow: {
    minHeight: 76,
    padding: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
  },
  artistBadge: {
    width: 44,
    height: 44,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.gold,
  },
  artistNumber: {
    fontSize: 17,
    fontWeight: "900",
    color: colors.ink,
  },
  artistName: {
    fontSize: 16,
    fontWeight: "800",
    color: colors.ink,
  },
  sketchGrid: {
    gap: 14,
  },
  sketchCard: {
    minHeight: 272,
    padding: 12,
    borderRadius: 8,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
    gap: 8,
    overflow: "hidden",
  },
  sketchLabel: {
    fontSize: 14,
    fontWeight: "800",
    color: colors.ink,
  },
  scorePanel: {
    padding: 22,
    borderRadius: 8,
    backgroundColor: colors.ink,
    gap: 8,
  },
  scoreNumber: {
    fontSize: 60,
    lineHeight: 66,
    fontWeight: "900",
    color: colors.gold,
  },
  scoreLabel: {
    fontSize: 15,
    fontWeight: "800",
    color: colors.paper,
  },
  feedback: {
    fontSize: 16,
    lineHeight: 24,
    color: "#F3F4F6",
  },
  resultLine: {
    padding: 16,
    borderRadius: 8,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.line,
    gap: 8,
  },
  resultText: {
    fontSize: 17,
    lineHeight: 24,
    color: colors.ink,
  },
  tags: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  tag: {
    minHeight: 34,
    paddingHorizontal: 10,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 8,
  },
  tagMint: {
    backgroundColor: "#DDF7EF",
  },
  tagCoral: {
    backgroundColor: "#FFE0DD",
  },
  tagText: {
    fontSize: 14,
    fontWeight: "800",
    color: colors.ink,
  },
});
