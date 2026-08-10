import { useState } from "react";
import { Alert, ScrollView, Text, TextInput, View } from "react-native";
import { Plus } from "lucide-react-native";
import { PrimaryButton } from "../components/Buttons";
import { colors, styles } from "../styles";
import type { Game } from "../types/game";

export function CreateGameScreen({
  currentUserId,
  onCreateGame,
}: {
  currentUserId: string;
  onCreateGame: (opponentUserId: string) => Promise<Game>;
}) {
  const [opponentId, setOpponentId] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit() {
    if (!opponentId.trim() || opponentId.trim() === currentUserId) {
      Alert.alert("Choose another user", "Paste another user ID or create a local opponent.");
      return;
    }
    setLoading(true);
    try {
      await onCreateGame(opponentId.trim());
    } catch (error) {
      Alert.alert("Could not create game", getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.sectionTitle}>Create game</Text>
      <View style={styles.fieldGroup}>
        <Text style={styles.label}>Opponent user ID</Text>
        <TextInput value={opponentId} onChangeText={setOpponentId} style={styles.input} placeholder="Paste user ID" placeholderTextColor={colors.muted} />
      </View>
      <View style={styles.row}>
        <View style={styles.rowFill}>
          <PrimaryButton label="Start" icon={<Plus size={20} color={colors.paper} />} onPress={submit} loading={loading} />
        </View>
      </View>
    </ScrollView>
  );
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Unknown error";
}
