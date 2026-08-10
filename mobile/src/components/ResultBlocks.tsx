import { Text, View } from "react-native";
import { styles } from "../styles";

export function ResultLine({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.resultLine}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.resultText}>{value}</Text>
    </View>
  );
}

export function TagBlock({
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
