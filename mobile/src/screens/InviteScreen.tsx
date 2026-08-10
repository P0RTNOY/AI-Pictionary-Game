import * as Clipboard from "expo-clipboard";
import { useEffect, useRef, useState } from "react";
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
  lifecycleEpoch,
  initialCode,
  onInitialCodeHandled,
  onJoined,
}: {
  userId: string;
  lifecycleEpoch: number;
  initialCode?: string | null;
  onInitialCodeHandled?: () => void;
  onJoined: (game: Game) => void;
}) {
  const [invite, setInvite] = useState<GameInvitePreview | null>(null);
  const [joinInviteStatus, setJoinInviteStatus] = useState<GameInvitePreview | null>(null);
  const [joinCode, setJoinCode] = useState(initialCode ?? "");
  const [busyAction, setBusyAction] = useState<"create" | "join" | "share" | null>(null);
  const [refreshingInvite, setRefreshingInvite] = useState(false);
  const [checkingInvite, setCheckingInvite] = useState(false);
  const actionInFlight = useRef(false);
  const actionController = useRef<AbortController | null>(null);
  const lookupController = useRef<AbortController | null>(null);
  const refreshController = useRef<AbortController | null>(null);
  const lookupGeneration = useRef(0);
  const actionGeneration = useRef(0);

  useEffect(() => {
    actionController.current?.abort();
    lookupController.current?.abort();
    refreshController.current?.abort();
    actionController.current = null;
    lookupController.current = null;
    refreshController.current = null;
    actionInFlight.current = false;
    actionGeneration.current += 1;
    lookupGeneration.current += 1;
    setBusyAction(null);
    setRefreshingInvite(false);
    setCheckingInvite(false);
    return () => {
      actionController.current?.abort();
      lookupController.current?.abort();
      refreshController.current?.abort();
    };
  }, [lifecycleEpoch]);

  useEffect(() => {
    if (!initialCode) return;
    const normalized = normalizeInviteCode(initialCode);
    setJoinCode(normalized);
    void lookupJoinInvite(normalized, true);
    onInitialCodeHandled?.();
  }, [initialCode]);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state !== "active") return;
      if (invite) void refreshCreatedInvite(true);
      if (joinCode.trim()) void lookupJoinInvite(joinCode, true);
    });
    return () => subscription.remove();
  }, [invite?.code, joinCode]);

  async function create() {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    actionGeneration.current += 1;
    const controller = new AbortController();
    actionController.current = controller;
    setBusyAction("create");
    try {
      const created = await createInvite(controller.signal);
      if (!controller.signal.aborted) setInvite(created);
    } catch (error) {
      if (!controller.signal.aborted) {
        captureError(error, { area: "invite_create", userId });
        Alert.alert("Could not create invite", error instanceof Error ? error.message : "Unknown error");
      }
    } finally {
      if (actionController.current === controller) {
        if (!controller.signal.aborted) setBusyAction(null);
        actionInFlight.current = false;
        actionController.current = null;
      }
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
    if (!invite || actionInFlight.current) return;
    actionInFlight.current = true;
    const generation = ++actionGeneration.current;
    setBusyAction("share");
    try {
      await Share.share({
        message: `Join my AI Pictionary game: ${buildInviteLink(invite.code)}\nCode: ${invite.code}`,
      });
      void refreshCreatedInvite(true);
    } finally {
      if (generation === actionGeneration.current) {
        actionInFlight.current = false;
        setBusyAction(null);
      }
    }
  }

  async function refreshCreatedInvite(silent = false) {
    if (!invite) return;
    refreshController.current?.abort();
    const controller = new AbortController();
    refreshController.current = controller;
    setRefreshingInvite(true);
    try {
      const refreshed = await getInvite(invite.code, controller.signal);
      if (!controller.signal.aborted) setInvite(refreshed);
    } catch (error) {
      if (!controller.signal.aborted) {
        captureError(error, { area: "invite_refresh" });
        if (!silent) Alert.alert("Could not refresh invite", error instanceof Error ? error.message : "Unknown error");
      }
    } finally {
      if (!controller.signal.aborted) setRefreshingInvite(false);
      if (refreshController.current === controller) refreshController.current = null;
    }
  }

  async function lookupJoinInvite(codeValue = joinCode, silent = false) {
    const normalized = normalizeInviteCode(codeValue);
    if (!normalized) return;
    const generation = ++lookupGeneration.current;
    lookupController.current?.abort();
    const controller = new AbortController();
    lookupController.current = controller;
    setCheckingInvite(true);
    try {
      const found = await getInvite(normalized, controller.signal);
      if (!controller.signal.aborted && generation === lookupGeneration.current) setJoinInviteStatus(found);
    } catch (error) {
      if (!controller.signal.aborted && generation === lookupGeneration.current) {
        captureError(error, { area: "invite_lookup" });
        setJoinInviteStatus(null);
        if (!silent) Alert.alert("Invite not found", friendlyInviteError(error));
      }
    } finally {
      if (!controller.signal.aborted && generation === lookupGeneration.current) setCheckingInvite(false);
      if (lookupController.current === controller) lookupController.current = null;
    }
  }

  async function join() {
    if (!joinCode.trim() || actionInFlight.current) return;
    actionInFlight.current = true;
    actionGeneration.current += 1;
    const controller = new AbortController();
    actionController.current = controller;
    setBusyAction("join");
    const code = normalizeInviteCode(joinCode);
    captureMessage("Invite code submitted", { area: "invite_join", userId });
    try {
      const game = await joinInvite(code, controller.signal);
      if (controller.signal.aborted) return;
      captureMessage("Invite join returned game", { area: "invite_join", gameId: game.id, currentTurnUserId: game.current_turn_user_id });
      onJoined(game);
    } catch (error) {
      if (!controller.signal.aborted) {
        captureError(error, { area: "invite_join", userId });
        Alert.alert("Could not join invite", friendlyInviteError(error));
      }
    } finally {
      if (actionController.current === controller) {
        if (!controller.signal.aborted) setBusyAction(null);
        actionInFlight.current = false;
        actionController.current = null;
      }
    }
  }

  const createdInviteStatus = statusText(invite, userId, "created");
  const joinStatus = statusText(joinInviteStatus, userId, "join");
  const cannotJoin =
    !joinCode.trim() ||
    busyAction !== null ||
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
            <PrimaryButton label="Create invite code" icon={<Plus size={20} color={colors.paper} />} onPress={create} loading={busyAction === "create"} disabled={busyAction !== null} />
          </View>
          {invite && <SecondaryButton label="Share invite" icon={<Share2 size={18} color={colors.ink} />} onPress={shareInvite} loading={busyAction === "share"} disabled={busyAction !== null} />}
        </View>
        {invite && (
          <View style={styles.row}>
            <SecondaryButton label="Copy invite code" icon={<ClipboardCopy size={18} color={colors.ink} />} onPress={copy} disabled={busyAction !== null || refreshingInvite} />
            <SecondaryButton label="Refresh invite status" icon={<RefreshCw size={18} color={colors.ink} />} onPress={() => refreshCreatedInvite()} loading={refreshingInvite} disabled={busyAction !== null} />
          </View>
        )}
        {invite && (
          <View style={styles.row}>
            <SecondaryButton label="Copy invite link" icon={<ClipboardCopy size={18} color={colors.ink} />} onPress={copyLink} disabled={busyAction !== null || refreshingInvite} />
          </View>
        )}
      </View>
      <View style={styles.panel}>
        <Text style={styles.gameTitle}>Join with code</Text>
        <TextInput
          value={joinCode}
          accessibilityLabel="Invite code"
          editable={busyAction === null}
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
        {joinCode.trim() && <Text style={styles.tinyText}>Status: {checkingInvite ? "Checking…" : joinStatus}</Text>}
        <View style={styles.row}>
          <View style={styles.rowFill}>
            <PrimaryButton label="Join game from invite" icon={<LogIn size={20} color={colors.paper} />} onPress={join} loading={busyAction === "join"} disabled={cannotJoin} />
          </View>
          <SecondaryButton label="Check invite status" icon={<RefreshCw size={18} color={colors.ink} />} onPress={() => lookupJoinInvite()} loading={checkingInvite} disabled={busyAction !== null} />
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
