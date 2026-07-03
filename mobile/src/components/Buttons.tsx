import type React from "react";
import { ActivityIndicator, Pressable, Text } from "react-native";
import { colors, styles } from "../styles";
import { tapHaptic } from "../utils/haptics";

export function PrimaryButton({
  label,
  icon,
  onPress,
  disabled,
  loading,
}: {
  label: string;
  icon?: React.ReactNode;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: Boolean(disabled || loading) }}
      disabled={disabled || loading}
      onPress={() => {
        tapHaptic();
        onPress();
      }}
      style={({ pressed }) => [styles.primaryButton, (disabled || loading) && styles.disabled, pressed && styles.pressed]}
    >
      {loading ? <ActivityIndicator color={colors.paper} /> : icon}
      <Text style={styles.primaryButtonText}>{label}</Text>
    </Pressable>
  );
}

export function SecondaryButton({ label, icon, onPress }: { label: string; icon?: React.ReactNode; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => {
        tapHaptic();
        onPress();
      }}
      style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}
    >
      {icon}
      <Text style={styles.secondaryButtonText}>{label}</Text>
    </Pressable>
  );
}
