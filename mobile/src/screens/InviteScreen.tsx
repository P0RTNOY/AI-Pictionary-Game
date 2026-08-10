import * as Clipboard from "expo-clipboard";
import { useEffect, useState } from "react";
import { Alert, AppState, ScrollView, Share, Text, TextInput, View } from "react-native";
import { ClipboardCopy, LogIn, Plus, RefreshCw, Share2 } from "lucide-react-native";
import { createInvite, getInvite, joinInvite } from "../api/invites";
import { PrimaryButton, SecondaryButton } from "../components/Buttons";
import { colors, styles } from "../styles";
import type { Game, GameInvitePreview } from "../types/game";
import { buildInviteLink, normalizeInviteCode } from "../utils/deepLinks";
import { captureError, captureMessage } from "../utils/errorReporter";

export function InviteScreen({
  userId,
  initialCode,
  onInitialCodeHandled,
  onJoined,
}: {
  userId: string;
  initialCode?: string | null;
  onInitialCodeHandled?: () => void;
  onJoined: (game: Game) => void;
}) {
  const [invite, setInvite] = useState<GameInvitePreview | null>(null);
  const [joinInviteStatus, setJoinInviteStatus] = useState<GameInvitePreview | null>(null);
  const [joinCode, setJoinCode] = useState(initialCode ?? "");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!initialCode) return;
    const normalized = normalizeInviteCode(initialCode);
    setJoinCode(normalized);
    lookupJoinInvite(normalized, true);
    onInitialCodeHandled?.();
  }, [initialCode]);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state !== "active") return;
      if (invite) refreshCreatedInvite(true);
      if (joinCode.trim()) lookupJoinInvite(joinCode, true);
    });
    return () => subscription.remove();
  }, [invite?.code, joinCode]);

  async function create() {
    setLoading(true);
    try {
      setInvite(await createInvite());
    } catch (error) {
      captureError(error, { area: "invite_create", userId });
      Alert.alert("Could not create invite", error instanceof Error ? error.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  async function copy() {
    if (!invite) return;
    await Clipboard.setStringAsync(invite.code);
    Alert.alert("Copied", "Invite code copied.");
  }

  async function copyLink() {
    if (!invite) return;
    await Clipboard.setStringAsync(buildInviteLink(invite.code));
    Alert.alert("Copied", "Invite link copied.");
  }

  async function shareInvite() {
    if (!invite) return;
    await Share.share({
      message: `Join my AI Pictionary game: ${buildInviteLink(invite.code)}\nCode: ${invite.code}`,
    });
    refreshCreatedInvite(true);
  }

  async function refreshCreatedInvite(silent = false) {
    if (!invite) return;
    try {
      setInvite(await getInvite(invite.code));
    } catch (error) {
      captureError(error, { area: "invite_refresh" });
      if (!silent) Alert.alert("Could not refresh invite", error instanceof Error ? error.message : "Unknown error");
    }
  }

  async function lookupJoinInvite(codeValue = joinCode, silent = false) {
    const normalized = normalizeInviteCode(codeValue);
    if (!normalized) return;
    try {
      const found = await getInvite(normalized);
      setJoinInviteStatus(found);
    } catch (error) {
      captureError(error, { area: "invite_lookup" });
      setJoinInviteStatus(null);
      if (!silent) Alert.alert("Invite not found", friendlyInviteError(error));
    }
  }

  async function join() {
    if (!joinCode.trim()) return;
    setLoading(true);
    const code = normalizeInviteCode(joinCode);
    captureMessage("Invite code submitted", { area: "invite_join", userId });
    try {
      const game = await joinInvite(code);
      captureMessage("Invite join returned game", { area: "invite_join", gameId: game.id, currentTurnUserId: game.current_turn_user_id });
      onJoined(game);
    } catch (error) {
      captureError(error, { area: "invite_join", userId });
      Alert.alert("Could not join invite", friendlyInviteError(error));
    } finally {
      setLoading(false);
    }
  }

  const createdInviteStatus = statusText(invite, userId, "created");
  const joinStatus = statusText(joinInviteStatus, userId, "join");
  const cannotJoin =
    !joinCode.trim() ||
    loading ||
    joinInviteStatus?.status === "accepted" ||
    joinInviteStatus?.status === "expired" ||
    joinInviteStatus?.creator_user_id === userId;

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.sectionTitle}>Invites</Text>
      <View style={styles.panel}>
        <Text style={styles.gameTitle}>Create an invite</Text>
        <Text style={styles.mutedText}>Send this to your friend. When they open it, they can join your game.</Text>
        {invite && (
          <View style={styles.inviteCodeBox}>
            <Text style={styles.inviteCode}>{invite.code}</Text>
          </View>
        )}
        {invite && <Text style={styles.tinyText}>Status: {createdInviteStatus}</Text>}
        {invite && <Text style={styles.tinyText}>Link format: {buildInviteLink(invite.code)}</Text>}
        <View style={styles.row}>
          <View style={styles.rowFill}>
            <PrimaryButton label="Create code" icon={<Plus size={20} color={colors.paper} />} onPress={create} loading={loading} />
          </View>
          {invite && <SecondaryButton label="Share" icon={<Share2 size={18} color={colors.ink} />} onPress={shareInvite} />}
        </View>
        {invite && (
          <View style={styles.row}>
            <SecondaryButton label="Copy code" icon={<ClipboardCopy size={18} color={colors.ink} />} onPress={copy} />
            <SecondaryButton label="Refresh" icon={<RefreshCw size={18} color={colors.ink} />} onPress={() => refreshCreatedInvite()} />
          </View>
        )}
        {invite && (
          <View style={styles.row}>
            <SecondaryButton label="Copy link" icon={<ClipboardCopy size={18} color={colors.ink} />} onPress={copyLink} />
          </View>
        )}
      </View>
      <View style={styles.panel}>
        <Text style={styles.gameTitle}>Join with code</Text>
        <TextInput
          value={joinCode}
          onChangeText={(value) => {
            setJoinCode(normalizeInviteCode(value));
            setJoinInviteStatus(null);
          }}
          onBlur={() => lookupJoinInvite()}
          autoCapitalize="none"
          autoCorrect={false}
          style={styles.input}
          placeholder="Paste invite code"
          placeholderTextColor={colors.muted}
        />
        {joinCode.trim() && <Text style={styles.tinyText}>Status: {joinStatus}</Text>}
        <View style={styles.row}>
          <View style={styles.rowFill}>
            <PrimaryButton label="Join game" icon={<LogIn size={20} color={colors.paper} />} onPress={join} loading={loading} disabled={cannotJoin} />
          </View>
          <SecondaryButton label="Check" icon={<RefreshCw size={18} color={colors.ink} />} onPress={() => lookupJoinInvite()} />
        </View>
      </View>
    </ScrollView>
  );
}

function statusText(invite: GameInvitePreview | null, userId: string, mode: "created" | "join") {
  if (!invite) return mode === "created" ? "No active invite" : "Enter a code to check";
  if (invite.status === "expired") return "Expired";
  if (invite.status === "accepted") return "Joined";
  if (invite.creator_user_id === userId && mode === "join") return "This is your own invite";
  return "Waiting for friend";
}

function friendlyInviteError(error: unknown) {
  const message = error instanceof Error ? error.message : "Unknown error";
  if (message.includes("Creator cannot join")) return "This is your own invite. Send it to your friend instead.";
  if (message.includes("Invite is not pending")) return "This invite was already joined or expired.";
  if (message.includes("Invite not found")) return "Check the code and try again.";
  return message;
}
