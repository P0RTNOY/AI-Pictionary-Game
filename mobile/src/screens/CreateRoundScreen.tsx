import { useEffect, useRef, useState } from "react";
import { Alert, ScrollView, Text, TextInput, View } from "react-native";
import { Dices, RefreshCw, Send } from "lucide-react-native";
import { createRound } from "../api/rounds";
import { PrimaryButton, SecondaryButton } from "../components/Buttons";
import { buildPrompt, promptPartLabels, promptPartPlaceholders, randomizePromptPart, randomPromptParts, type PromptParts } from "../promptRandomizer";
import { colors, styles } from "../styles";
import type { Game, Round } from "../types/game";
import { captureError, captureMessage } from "../utils/errorReporter";

const promptKeys: (keyof PromptParts)[] = ["character", "action", "setting", "twist"];

export function CreateRoundScreen({
  game,
  userId,
  onCreated,
}: {
  game: Game;
  userId: string;
  onCreated: (round: Round) => void;
}) {
  const [parts, setParts] = useState(randomPromptParts());
  const [prompt, setPrompt] = useState(() => buildPrompt(parts));
  const [loading, setLoading] = useState(false);
  const submitInFlight = useRef(false);
  const submitController = useRef<AbortController | null>(null);

  useEffect(() => () => submitController.current?.abort(), []);

  function updatePart(key: keyof PromptParts, value: string) {
    const next = { ...parts, [key]: value };
    setParts(next);
    setPrompt(buildPrompt(next));
  }

  function randomizeAll() {
    const next = randomPromptParts();
    setParts(next);
    setPrompt(buildPrompt(next));
  }

  function randomizeOne(key: keyof PromptParts) {
    const next = randomizePromptPart(parts, key);
    setParts(next);
    setPrompt(buildPrompt(next));
  }

  async function submit() {
    if (submitInFlight.current) return;
    if (prompt.trim().length < 6) {
      Alert.alert("Add a clearer prompt", "Write at least a few words.");
      return;
    }
    submitInFlight.current = true;
    const controller = new AbortController();
    submitController.current = controller;
    setLoading(true);
    const promptToSubmit = prompt.trim();
    captureMessage("Round prompt submitted", { area: "round_create", gameId: game.id, creatorUserId: userId });
    try {
      const round = await createRound(game.id, promptToSubmit, controller.signal);
      if (controller.signal.aborted) return;
      captureMessage("Round created from prompt", {
        area: "round_create",
        roundId: round.id,
        gameId: game.id,
      });
      onCreated(round);
    } catch (error) {
      captureError(error, { area: "round_create", gameId: game.id, creatorUserId: userId });
      if (!controller.signal.aborted) Alert.alert("Could not create round", error instanceof Error ? error.message : "Unknown error");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
      submitInFlight.current = false;
      if (submitController.current === controller) submitController.current = null;
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.sectionTitle}>Your prompt</Text>
      <Text style={styles.mutedText}>Build a scene the AI artists can draw, but your opponent will only see the sketches.</Text>
      <View style={styles.builderGrid}>
        {promptKeys.map((key) => (
          <View key={key} style={styles.promptPartCard}>
            <View style={styles.promptPartHeader}>
              <Text style={styles.label}>{promptPartLabels[key]}</Text>
              <SecondaryButton label={`Roll ${promptPartLabels[key]}`} icon={<Dices size={16} color={colors.ink} />} onPress={() => randomizeOne(key)} disabled={loading} />
            </View>
            <TextInput
              accessibilityLabel={promptPartLabels[key]}
              value={parts[key]}
              editable={!loading}
              onChangeText={(value) => updatePart(key, value)}
              style={styles.promptPartInput}
              placeholder={promptPartPlaceholders[key]}
              placeholderTextColor={colors.muted}
            />
          </View>
        ))}
      </View>
      <View style={styles.fieldGroup}>
        <Text style={styles.label}>Final prompt</Text>
        <TextInput
          accessibilityLabel="Situation prompt"
          multiline
          editable={!loading}
          value={prompt}
          onChangeText={setPrompt}
          style={styles.promptInput}
          textAlignVertical="top"
          placeholder="a giraffe teaching a dolphin piano"
          placeholderTextColor={colors.muted}
        />
      </View>
      <View style={styles.row}>
        <SecondaryButton label="Randomize all prompt parts" icon={<RefreshCw size={18} color={colors.ink} />} onPress={randomizeAll} disabled={loading} />
        <View style={styles.rowFill}>
          <PrimaryButton label="Generate" icon={<Send size={19} color={colors.paper} />} onPress={submit} loading={loading} />
        </View>
      </View>
    </ScrollView>
  );
}
