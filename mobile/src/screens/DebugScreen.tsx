import * as Clipboard from "expo-clipboard";
import { useState } from "react";
import { Alert, ScrollView, Text, View } from "react-native";
import { Bell, ClipboardCopy, RefreshCw } from "lucide-react-native";
import { API_URL } from "../api/client";
import type { AIStatus } from "../api/ai";
import { sendTestNotification } from "../api/debug";
import { PrimaryButton, SecondaryButton } from "../components/Buttons";
import { colors, styles } from "../styles";
import type { Round, User } from "../types/game";

export type DebugInfo = {
  realtimeConnected: boolean;
  fallbackPolling: boolean;
  lastEventId: number;
  lastEventType: string | null;
  pushPermissionStatus: string;
  pushToken: string | null;
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
  aiStatus,
  info,
}: {
  user: User;
  selectedGameId: string | null;
  selectedRound: Round | null;
  diagnostics: Record<string, unknown>;
  backendHealth: { status: "unknown" | "ok" | "unreachable"; message: string };
  onRefreshBackendHealth: () => void;
  aiStatus: AIStatus | null;
  info: DebugInfo;
}) {
  const [sending, setSending] = useState(false);

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
          ...info,
        },
        null,
        2,
      ),
    );
    Alert.alert("Copied", "Full debug info copied.");
  }

  async function sendPush() {
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
      setSending(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Text style={styles.sectionTitle}>Beta debug</Text>
      <Text style={styles.mutedText}>Useful when a build behaves differently on a phone or dev network.</Text>
      <View style={styles.panel}>
        <DebugLine label="App" value={`${diagnostics.appName ?? "AI Pictionary"} ${diagnostics.appVersion ?? ""}`} />
        <DebugLine label="Environment" value={`${diagnostics.appEnv ?? "unknown"} / ${diagnostics.buildProfile ?? "unknown"}`} />
        <DebugLine label="API" value={API_URL} />
        <DebugLine label="Backend health" value={`${backendHealth.status}: ${backendHealth.message}`} />
        <DebugLine label="AI provider" value={aiStatus ? `${aiStatus.runtime_provider} / judge ${aiStatus.judge_model}` : "Unknown"} />
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
            <DebugLine label="SVG Tiers" value={selectedRound.generated_svgs.map(s => s.model_tier).join(", ") || "None"} />
          </>
        )}
        <View style={{ marginVertical: 8, borderTopWidth: 1, borderTopColor: colors.line }} />

        <DebugLine label="Realtime" value={info.realtimeConnected ? "WebSocket connected" : info.fallbackPolling ? "Polling fallback" : "Idle"} />
        <DebugLine label="Last event" value={info.lastEventType ? `#${info.lastEventId} ${info.lastEventType}` : "None yet"} />
        <DebugLine label="Push permission" value={info.pushPermissionStatus} />
        <DebugLine label="Push token" value={info.pushToken ? `Registered (${info.pushToken.slice(0, 24)}...)` : info.pushError || "Not registered"} />
      </View>
      <PrimaryButton label="Send test notification" icon={<Bell size={20} color={colors.paper} />} onPress={sendPush} loading={sending} />
      <SecondaryButton label="Check backend health" icon={<RefreshCw size={18} color={colors.ink} />} onPress={onRefreshBackendHealth} />
      <SecondaryButton label="Refresh push token" icon={<RefreshCw size={18} color={colors.ink} />} onPress={info.refreshPushRegistration} />
      <SecondaryButton label="Copy full debug info" icon={<ClipboardCopy size={18} color={colors.ink} />} onPress={copy} />
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
