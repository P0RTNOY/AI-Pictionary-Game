import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { Bug, Edit3, Link, Plus, RefreshCw, Sparkles } from "lucide-react-native";
import { PrimaryButton, SecondaryButton } from "../components/Buttons";
import { StatusPill, statusForGame } from "../components/StatusPill";
import { colors, styles } from "../styles";
import type { Game, User } from "../types/game";

export function HomeScreen({
  user,
  games,
  backendHealth,
  onCreateGame,
  onRefresh,
  refreshing,
  onEditProfile,
  onOpenGame,
  onOpenDebug,
}: {
  user: User;
  games: Game[];
  backendHealth: { status: "unknown" | "ok" | "unreachable"; message: string };
  onCreateGame: () => void;
  onRefresh: () => void;
  refreshing: boolean;
  onEditProfile: () => void;
  onOpenGame: (game: Game) => void;
  onOpenDebug: () => void;
}) {
  const yourTurn = games.filter((game) => isYourTurn(game, user.id));
  const waiting = games.filter((game) => !isYourTurn(game, user.id) && game.status === "active" && game.latest_round?.status !== "guessed");
  const completed = games.filter((game) => !yourTurn.includes(game) && !waiting.includes(game));

  return (
    <ScrollView contentContainerStyle={styles.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}>
      <View style={styles.hero}>
        <View style={styles.heroIcon}>
          <Sparkles size={30} color={colors.ink} strokeWidth={2.2} />
        </View>
        <Text style={styles.title}>AI Pictionary</Text>
        <Text style={styles.subtitle}>Async sketch duels between two local players.</Text>
      </View>

      <View style={styles.panel}>
        <View style={styles.row}>
          <View style={[styles.avatarSmall, { backgroundColor: user.avatar_color }]}>
            <Text style={styles.avatarSmallText}>{user.avatar_emoji}</Text>
          </View>
          <View style={styles.gameRowMain}>
            <Text style={styles.label}>Your profile</Text>
            <Text style={styles.resultText}>{user.display_name}</Text>
          </View>
          <SecondaryButton label="Edit" icon={<Edit3 size={16} color={colors.ink} />} onPress={onEditProfile} />
        </View>
        <SecondaryButton label="Beta debug" icon={<Bug size={16} color={colors.ink} />} onPress={onOpenDebug} />
      </View>

      {backendHealth.status === "unreachable" && (
        <View style={styles.panel}>
          <Text style={styles.gameTitle}>Backend unreachable</Text>
          <Text style={styles.mutedText}>{backendHealth.message}</Text>
          <SecondaryButton label="Retry" icon={<RefreshCw size={18} color={colors.ink} />} onPress={onRefresh} />
        </View>
      )}

      {games.length ? (
        <>
          <GameSection title="Your turn" games={yourTurn} user={user} empty="Nothing needs you right now." onOpenGame={onOpenGame} />
          <GameSection title="Waiting" games={waiting} user={user} empty="No games are waiting on someone else." onOpenGame={onOpenGame} />
          <GameSection title="Completed" games={completed} user={user} empty="Completed rounds will appear here." onOpenGame={onOpenGame} />
        </>
      ) : (
        <View style={styles.panel}>
          <Text style={styles.gameTitle}>No games yet</Text>
          <Text style={styles.mutedText}>Create an invite code or join one from another player.</Text>
        </View>
      )}

      <View style={styles.row}>
        <View style={styles.rowFill}>
          <PrimaryButton label="Create invite" icon={<Plus size={20} color={colors.paper} />} onPress={onCreateGame} />
        </View>
        <SecondaryButton label="Join" icon={<Link size={18} color={colors.ink} />} onPress={onCreateGame} />
        <SecondaryButton label="Refresh" icon={<RefreshCw size={18} color={colors.ink} />} onPress={onRefresh} />
      </View>
    </ScrollView>
  );
}

function GameSection({
  title,
  games,
  user,
  empty,
  onOpenGame,
}: {
  title: string;
  games: Game[];
  user: User;
  empty: string;
  onOpenGame: (game: Game) => void;
}) {
  return (
    <View style={{ gap: 10 }}>
      <Text style={styles.sectionHeader}>{title}</Text>
      {games.length ? games.map((game) => <GameRow key={game.id} game={game} user={user} onOpenGame={onOpenGame} />) : <Text style={styles.mutedText}>{empty}</Text>}
    </View>
  );
}

function GameRow({ game, user, onOpenGame }: { game: Game; user: User; onOpenGame: (game: Game) => void }) {
  const opponent = game.opponent;
  const status = statusForGame(game, user.id);
  const isNew = game.latest_round?.status === "ready_to_guess" && game.latest_round.guesser_user_id === user.id;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Open game"
      onPress={() => onOpenGame(game)}
      style={({ pressed }) => [styles.gameRow, pressed && styles.pressed]}
    >
      <View style={[styles.avatarSmall, { backgroundColor: opponent?.avatar_color ?? colors.gold }]}>
        <Text style={styles.avatarSmallText}>{opponent?.avatar_emoji ?? "?"}</Text>
      </View>
      <View style={styles.gameRowMain}>
        <View style={styles.gameRowMeta}>
          <Text style={styles.gameTitle}>{opponent ? opponent.display_name : `Game ${game.id.slice(0, 8)}`}</Text>
          {isNew && (
            <View style={styles.newBadge}>
              <Text style={styles.newBadgeText}>New</Text>
            </View>
          )}
        </View>
        <Text style={styles.gamePrompt} numberOfLines={2}>
          {gameDescription(game, user.id)}
        </Text>
        <Text style={styles.tinyText}>Last activity {formatRelative(game.latest_round?.updated_at ?? game.updated_at)}</Text>
      </View>
      <StatusPill status={status} />
    </Pressable>
  );
}

function isYourTurn(game: Game, userId: string) {
  const latest = game.latest_round;
  if (!latest || latest.status === "guessed") return game.current_turn_user_id === userId;
  return latest.status === "ready_to_guess" && latest.guesser_user_id === userId;
}

function gameDescription(game: Game, userId: string) {
  const latest = game.latest_round;
  if (latest?.status === "guessed") return latest.guess?.short_feedback ?? "Round scored.";
  if (latest?.status === "ready_to_guess") return latest.guesser_user_id === userId ? "Sketches are ready. Make your guess." : "Waiting for opponent to guess.";
  if (latest?.status === "generating") return "AI artists are drawing.";
  return game.current_turn_user_id === userId ? "Create the next prompt." : "Waiting for opponent to create a prompt.";
}

function formatRelative(value: string) {
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return "recently";
  const minutes = Math.max(0, Math.floor((Date.now() - time) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
