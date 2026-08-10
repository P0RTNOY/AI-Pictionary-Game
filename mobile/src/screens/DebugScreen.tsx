import * as Clipboard from "expo-clipboard";
import { useRef, useState } from "react";
import { Alert, ScrollView, Text, View } from "react-native";
import { Bell, ClipboardCopy, RefreshCw, Trash2 } from "lucide-react-native";
import { API_URL } from "../api/client";
import type { AIStatus } from "../api/ai";
import { resetBackendData, sendTestNotification } from "../api/debug";
import { PrimaryButton, SecondaryButton } from "../components/Buttons";
import { colors, styles } from "../styles";
import type { Round, User } from "../types/game";

export type DebugInfo = {
  realtimeConnected: boolean;
  fallbackPolling: boolean;
  lastEventId: number;
  lastEventType: string | null;
  pushPermissionStatus: string;
  pushRegistered: boolean;
  pushTokenFingerprint: string | null;
  pushError: string | null;
  refreshPushRegistration: () => void;
};

export function DebugScreen({
  user,
  selectedGameId,
  selectedRound,
  diagnostics,
  backendHealth,
  onRefreshBackendHealth,
  onResetLocalState,
  onBackendResetComplete,
  aiStatus,
  info,
}: {
  user: User;
  selectedGameId: string | null;
  selectedRound: Round | null;
  diagnostics: Record<string, unknown>;
  backendHealth: { status: "unknown" | "ok" | "unreachable"; message: string };
  onRefreshBackendHealth: () => void;
  onResetLocalState: () => Promise<void>;
  onBackendResetComplete: () => Promise<void>;
  aiStatus: AIStatus | null;
  info: DebugInfo;
}) {
  const [sending, setSending] = useState(false);
  const [localResetting, setLocalResetting] = useState(false);
  const [backendResetting, setBackendResetting] = useState(false);
  const sendInFlight = useRef(false);
  const resetDialogOpen = useRef(false);

  async function copy() {
    await Clipboard.setStringAsync(
      JSON.stringify(
        {
          apiUrl: API_URL,
          userId: user.id,
          displayName: user.display_name,
          selectedGameId,
          selectedRoundId: selectedRound?.id,
          backendHealth,
          diagnostics,
          aiStatus,
          realtimeConnected: info.realtimeConnected,
          fallbackPolling: info.fallbackPolling,
          lastEventId: info.lastEventId,
          lastEventType: info.lastEventType,
          pushPermissionStatus: info.pushPermissionStatus,
          pushRegistered: info.pushRegistered,
          pushTokenFingerprint: info.pushTokenFingerprint,
          pushError: info.pushError,
        },
        null,
        2,
      ),
    );
    Alert.alert("Copied", "Full debug info copied.");
  }

  async function sendPush() {
    if (sendInFlight.current) return;
    sendInFlight.current = true;
    setSending(true);
    try {
      const result = await sendTestNotification(user.id, selectedGameId);
      Alert.alert(
        "Test notification queued",
        result.active_device_tokens
          ? `Provider: ${result.provider}. Active tokens: ${result.active_device_tokens}.`
          : "No active device token is registered yet. Check notification permission and token status.",
      );
    } catch (error) {
      Alert.alert("Could not send test notification", error instanceof Error ? error.message : "Unknown error");
    } finally {
      sendInFlight.current = false;
      setSending(false);
    }
  }

  function handleResetLocal() {
    if (resetDialogOpen.current || localResetting || backendResetting) return;
    resetDialogOpen.current = true;
    Alert.alert(
      "Reset local app state?",
      "This clears this device’s local user/profile/onboarding state. You will return to first launch. Continue?",
      [
        { text: "Cancel", style: "cancel", onPress: () => { resetDialogOpen.current = false; } },
        {
          text: "Reset",
          style: "destructive",
          onPress: async () => {
            setLocalResetting(true);
            try {
              await onResetLocalState();
            } catch (error) {
              Alert.alert("Could not reset local state", error instanceof Error ? error.message : "Unknown error");
            } finally {
              resetDialogOpen.current = false;
              setLocalResetting(false);
            }
          },
        },
      ],
      { onDismiss: () => { resetDialogOpen.current = false; } },
    );
  }

  function handleResetBackend() {
    if (resetDialogOpen.current || localResetting || backendResetting) return;
    resetDialogOpen.current = true;
    Alert.alert(
      "Reset backend local data?",
      "This deletes all local users, games, rounds, invites, events, device tokens and notification attempts from the current backend database. Continue?",
      [
        { text: "Cancel", style: "cancel", onPress: () => { resetDialogOpen.current = false; } },
        {
          text: "Reset",
          style: "destructive",
          onPress: async () => {
            setBackendResetting(true);
            try {
              const res = await resetBackendData();
              await onBackendResetComplete();
              Alert.alert("Backend reset successful", `Deleted ${res.deleted_rows} local rows. This device returned to onboarding.`);
            } catch (error) {
              Alert.alert("Could not reset backend", error instanceof Error ? error.message : "Unknown error");
            } finally {
              resetDialogOpen.current = false;
              setBackendResetting(false);
            }
          },
        },
      ],
      { onDismiss: () => { resetDialogOpen.current = false; } },
    );
  }

  const showBackendReset =
    backendHealth.status === "ok" &&
    (diagnostics.appEnv === "development" || diagnostics.appEnv === "local" || diagnostics.appEnv === "test");
  const resetInProgress = localResetting || backendResetting;

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.sectionTitle}>Beta debug</Text>
      <Text style={styles.mutedText}>Useful when a build behaves differently on a phone or dev network.</Text>
      <View style={styles.panel}>
        <DebugLine label="App" value={`${diagnostics.appName ?? "AI Pictionary"} ${diagnostics.appVersion ?? ""}`} />
        <DebugLine label="Environment" value={`${diagnostics.appEnv ?? "unknown"} / ${diagnostics.buildProfile ?? "unknown"}`} />
        <DebugLine label="API" value={API_URL} />
        <DebugLine label="Backend health" value={`${backendHealth.status}: ${backendHealth.message}`} />
        <DebugLine label="AI provider" value={aiStatus ? aiStatus.runtime_provider : "Unknown"} />
        <DebugLine label="Judge model" value={aiStatus ? aiStatus.judge_model : "Unknown"} />
        <DebugLine
          label="Configured"
          value={aiStatus ? `OpenRouter: ${aiStatus.openrouter_configured ? "Yes" : "No"}, Local: ${aiStatus.local_model_configured ? "Yes" : "No"}` : "Unknown"}
        />
        {aiStatus?.artist_models && (
          <DebugLine label="Artist models" value={aiStatus.artist_models.map((model) => `${model.tier}: ${model.model}`).join("\n")} />
        )}
        {aiStatus?.mock_mode_notice && <DebugLine label="Mock mode" value={aiStatus.mock_mode_notice} />}
        <DebugLine label="User" value={`${user.display_name} (${user.id.slice(0, 8)})`} />

        <View style={{ marginVertical: 8, borderTopWidth: 1, borderTopColor: colors.line }} />
        <DebugLine label="Active Game ID" value={selectedGameId ?? "None"} />
        {selectedRound && (
          <>
            <DebugLine label="Active Round ID" value={selectedRound.id} />
            <DebugLine label="Round Game ID" value={selectedRound.game_id} />
            {selectedRound.original_prompt ? (
              <DebugLine label="Original Prompt" value={selectedRound.original_prompt} />
            ) : null}
            <DebugLine label="Round Provider" value={selectedRound.generated_svgs[0]?.provider_used ?? "Unknown"} />
            <DebugLine label="SVG Tiers" value={selectedRound.generated_svgs.map((svg) => svg.model_tier).join(", ") || "None"} />
          </>
        )}
        <View style={{ marginVertical: 8, borderTopWidth: 1, borderTopColor: colors.line }} />

        <DebugLine label="Realtime" value={info.realtimeConnected ? "WebSocket connected" : info.fallbackPolling ? "Polling fallback" : "Idle"} />
        <DebugLine label="Last event" value={info.lastEventType ? `#${info.lastEventId} ${info.lastEventType}` : "None yet"} />
        <DebugLine label="Push permission" value={info.pushPermissionStatus} />
        <DebugLine
          label="Push registration"
          value={
            info.pushRegistered
              ? `Registered${info.pushTokenFingerprint ? ` (${info.pushTokenFingerprint})` : ""}`
              : info.pushError || "Not registered"
          }
        />
      </View>
      <PrimaryButton label="Send test notification" icon={<Bell size={20} color={colors.paper} />} onPress={sendPush} loading={sending} />
      <SecondaryButton label="Check backend health" icon={<RefreshCw size={18} color={colors.ink} />} onPress={onRefreshBackendHealth} />
      <SecondaryButton label="Refresh push token" icon={<RefreshCw size={18} color={colors.ink} />} onPress={info.refreshPushRegistration} />
      <SecondaryButton label="Copy full debug info" icon={<ClipboardCopy size={18} color={colors.ink} />} onPress={copy} />

      <View style={{ marginTop: 24, marginBottom: 8 }}>
        <Text style={[styles.label, { color: colors.coral }]}>Danger Zone</Text>
      </View>
      <SecondaryButton
        label="Reset local app state"
        icon={<Trash2 size={18} color={colors.coral} />}
        onPress={handleResetLocal}
        loading={localResetting}
        disabled={resetInProgress}
      />
      {showBackendReset && (
        <SecondaryButton
          label="Reset backend local data"
          icon={<Trash2 size={18} color={colors.coral} />}
          onPress={handleResetBackend}
          loading={backendResetting}
          disabled={resetInProgress}
        />
      )}
    </ScrollView>
  );
}

function DebugLine({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.debugLine}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.resultText}>{value}</Text>
    </View>
  );
}
