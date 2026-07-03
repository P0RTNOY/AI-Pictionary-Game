import { useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { Eye, Palette, Trophy } from "lucide-react-native";
import { PrimaryButton, SecondaryButton } from "../components/Buttons";
import { colors, styles } from "../styles";

const steps = [
  {
    title: "Create a weird prompt",
    body: "Build a strange scene, then send it to three AI artists who draw it in different ways.",
    icon: Palette,
  },
  {
    title: "Your friend guesses",
    body: "They see the sketches, not your original prompt. Extra sketches are clues.",
    icon: Eye,
  },
  {
    title: "Fewer clues score higher",
    body: "One clue keeps the full score. Revealing more clues makes the guess easier and adds a penalty.",
    icon: Trophy,
  },
];

export function OnboardingScreen({ onDone }: { onDone: () => void }) {
  const [index, setIndex] = useState(0);
  const step = steps[index];
  const Icon = step.icon;
  const isLast = index === steps.length - 1;

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.onboardingHero}>
        <View style={styles.heroIcon}>
          <Icon size={30} color={colors.ink} />
        </View>
        <Text style={styles.title}>{step.title}</Text>
        <Text style={styles.subtitle}>{step.body}</Text>
      </View>
      <View style={styles.progressDots}>
        {steps.map((item, dotIndex) => (
          <View key={item.title} style={[styles.progressDot, dotIndex === index && styles.progressDotActive]} />
        ))}
      </View>
      <PrimaryButton label={isLast ? "Set up profile" : "Next"} onPress={isLast ? onDone : () => setIndex((current) => current + 1)} />
      <SecondaryButton label="Skip" onPress={onDone} />
    </ScrollView>
  );
}
