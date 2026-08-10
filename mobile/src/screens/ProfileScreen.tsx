import { useEffect, useRef, useState } from "react";
import { Alert, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { Check } from "lucide-react-native";
import { PrimaryButton, SecondaryButton } from "../components/Buttons";
import { colors, styles } from "../styles";
import type { User } from "../types/game";

const colorChoices = [
  { name: "Gold", value: "#F5C84C" },
  { name: "Mint", value: "#24A98C" },
  { name: "Blue", value: "#4E79FF" },
  { name: "Coral", value: "#FF6B5F" },
];

export function ProfileScreen({
  user,
  onSave,
  onCancel,
}: {
  user: User | null;
  onSave: (payload: { display_name: string; avatar_emoji: string; avatar_color: string }, signal: AbortSignal) => Promise<void>;
  onCancel?: () => void;
}) {
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [avatarEmoji, setAvatarEmoji] = useState(user?.avatar_emoji ?? "🙂");
  const [avatarColor, setAvatarColor] = useState(user?.avatar_color ?? colorChoices[0].value);
  const [loading, setLoading] = useState(false);
  const saveInFlight = useRef(false);
  const saveController = useRef<AbortController | null>(null);

  useEffect(() => () => saveController.current?.abort(), []);

  async function submit() {
    if (saveInFlight.current) return;
    if (!displayName.trim()) {
      Alert.alert("Name required", "Add a display name before continuing.");
      return;
    }
    saveInFlight.current = true;
    const controller = new AbortController();
    saveController.current = controller;
    setLoading(true);
    try {
      await onSave({ display_name: displayName.trim(), avatar_emoji: avatarEmoji.trim() || "🙂", avatar_color: avatarColor }, controller.signal);
    } catch (error) {
      if (!controller.signal.aborted) Alert.alert("Could not save profile", error instanceof Error ? error.message : "Unknown error");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
      saveInFlight.current = false;
      if (saveController.current === controller) saveController.current = null;
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.sectionTitle}>{user ? "Edit profile" : "Choose your name"}</Text>
      <View style={styles.panel}>
        <View style={[styles.avatarPreview, { backgroundColor: avatarColor }]}>
          <Text style={styles.avatarText}>{avatarEmoji}</Text>
        </View>
        <View style={styles.fieldGroup}>
          <Text style={styles.label}>Display name</Text>
          <TextInput
            accessibilityLabel="Display name"
            autoCapitalize="words"
            editable={!loading}
            value={displayName}
            onChangeText={setDisplayName}
            style={styles.input}
            placeholder="Omer"
            placeholderTextColor={colors.muted}
          />
        </View>
        <View style={styles.fieldGroup}>
          <Text style={styles.label}>Avatar mark</Text>
          <TextInput
            accessibilityLabel="Avatar mark"
            editable={!loading}
            value={avatarEmoji}
            onChangeText={setAvatarEmoji}
            style={styles.input}
            maxLength={4}
            placeholder="🙂"
            placeholderTextColor={colors.muted}
          />
        </View>
        <View style={styles.fieldGroup}>
          <Text style={styles.label}>Avatar color</Text>
          <View style={styles.colorRow}>
            {colorChoices.map((choice) => (
              <Pressable
                key={choice.value}
                accessibilityRole="button"
                accessibilityLabel={`${choice.name} avatar color`}
                accessibilityState={{ selected: avatarColor === choice.value }}
                onPress={() => setAvatarColor(choice.value)}
                disabled={loading}
                style={({ pressed }) => [
                  styles.colorSwatch,
                  { backgroundColor: choice.value },
                  avatarColor === choice.value && styles.colorSwatchSelected,
                  pressed && styles.pressed,
                ]}
              >
                {avatarColor === choice.value && <Check size={20} color={colors.ink} strokeWidth={3} />}
              </Pressable>
            ))}
          </View>
        </View>
      </View>
      <PrimaryButton label="Save" icon={<Check size={20} color={colors.paper} />} onPress={submit} loading={loading} />
      {onCancel && <SecondaryButton label="Cancel profile editing" onPress={onCancel} disabled={loading} />}
    </ScrollView>
  );
}
