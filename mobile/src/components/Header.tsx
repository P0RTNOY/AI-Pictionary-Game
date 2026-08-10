import { ArrowLeft, Home } from "lucide-react-native";
import { Pressable, Text, View } from "react-native";
import { colors, styles } from "../styles";

export function Header({ showBack, onHome, onBack }: { showBack: boolean; onHome: () => void; onBack: () => void }) {
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
