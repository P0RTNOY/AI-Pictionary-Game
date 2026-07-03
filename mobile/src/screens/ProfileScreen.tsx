import { useState } from "react";
import { Alert, ScrollView, Text, TextInput, View } from "react-native";
import { Check } from "lucide-react-native";
import { PrimaryButton, SecondaryButton } from "../components/Buttons";
import { colors, styles } from "../styles";
import type { User } from "../types/game";

const colorChoices = ["#F5C84C", "#24A98C", "#4E79FF", "#FF6B5F"];

export function ProfileScreen({
  user,
  onSave,
  onCancel,
}: {
  user: User | null;
  onSave: (payload: { display_name: string; avatar_emoji: string; avatar_color: string }) => Promise<void>;
  onCancel?: () => void;
}) {
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [avatarEmoji, setAvatarEmoji] = useState(user?.avatar_emoji ?? "🙂");
  const [avatarColor, setAvatarColor] = useState(user?.avatar_color ?? colorChoices[0]);
  const [loading, setLoading] = useState(false);

  async function submit() {
    if (!displayName.trim()) {
      Alert.alert("Name required", "Add a display name before continuing.");
      return;
    }
    setLoading(true);
    try {
      await onSave({ display_name: displayName.trim(), avatar_emoji: avatarEmoji.trim() || "🙂", avatar_color: avatarColor });
    } catch (error) {
      Alert.alert("Could not save profile", error instanceof Error ? error.message : "Unknown error");
    } finally {
      setLoading(false);
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
          <TextInput value={displayName} onChangeText={setDisplayName} style={styles.input} placeholder="Omer" placeholderTextColor={colors.muted} />
        </View>
        <View style={styles.fieldGroup}>
          <Text style={styles.label}>Avatar mark</Text>
          <TextInput value={avatarEmoji} onChangeText={setAvatarEmoji} style={styles.input} maxLength={4} placeholder="🙂" placeholderTextColor={colors.muted} />
        </View>
        <View style={styles.colorRow}>
          {colorChoices.map((color) => (
            <SecondaryButton key={color} label={avatarColor === color ? "Selected" : color} onPress={() => setAvatarColor(color)} />
          ))}
        </View>
      </View>
      <PrimaryButton label="Save" icon={<Check size={20} color={colors.paper} />} onPress={submit} loading={loading} />
      {onCancel && <SecondaryButton label="Cancel" onPress={onCancel} />}
    </ScrollView>
  );
}
