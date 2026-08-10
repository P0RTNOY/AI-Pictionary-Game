import AsyncStorage from "@react-native-async-storage/async-storage";
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, AppState, KeyboardAvoidingView, Linking, Platform, SafeAreaView } from "react-native";

import { configureApiCredential, healthCheck, isUnauthorizedError } from "./src/api/client";
import { getAIStatus, type AIStatus } from "./src/api/ai";
import { getGame, getGameStats, listGames } from "./src/api/games";
import { createUser, getUser, updateUser } from "./src/api/users";
import { Header } from "./src/components/Header";
import { useGameEvents } from "./src/hooks/useGameEvents";
import { usePushNotifications } from "./src/hooks/usePushNotifications";
import { CreateRoundScreen } from "./src/screens/CreateRoundScreen";
import { DebugScreen } from "./src/screens/DebugScreen";
import { GamePendingScreen } from "./src/screens/GamePendingScreen";
import { GuessScreen } from "./src/screens/GuessScreen";
import { HomeScreen } from "./src/screens/HomeScreen";
import { InviteScreen } from "./src/screens/InviteScreen";
import { OnboardingScreen } from "./src/screens/OnboardingScreen";
import { ProfileScreen } from "./src/screens/ProfileScreen";
import { ResultScreen } from "./src/screens/ResultScreen";
import { WaitingScreen } from "./src/screens/WaitingScreen";
import { styles } from "./src/styles";
import type { Game, GameStats, GuessResult, Round, User } from "./src/types/game";
import { appDiagnostics } from "./src/config";
import { parseInviteCodeFromUrl } from "./src/utils/deepLinks";
import { captureError, captureMessage } from "./src/utils/errorReporter";
import { decideSessionBootstrap } from "./src/sessionBootstrap";

type Screen = "onboarding" | "home" | "profile_setup" | "edit_profile" | "invites" | "create_round" | "waiting" | "guess" | "result" | "debug" | "startup_error";

const USER_ID_KEY = "ai-pictionary:user-id";
const SESSION_TOKEN_KEY = "ai-pictionary:session-token";
const ONBOARDING_KEY = "ai-pictionary:onboarding-complete";

export default function App() {
  const [screen, setScreen] = useState<Screen>("home");
  const [user, setUser] = useState<User | null>(null);
  const [games, setGames] = useState<Game[]>([]);
  const [selectedGame, setSelectedGame] = useState<Game | null>(null);
  const [selectedRound, setSelectedRound] = useState<Round | null>(null);
  const [selectedStats, setSelectedStats] = useState<GameStats | null>(null);
  const [pendingInviteCode, setPendingInviteCode] = useState<string | null>(null);
  const [backendHealth, setBackendHealth] = useState<{ status: "unknown" | "ok" | "unreachable"; message: string }>({
    status: "unknown",
    message: "Not checked yet",
  });
  const [selectedGameError, setSelectedGameError] = useState<string | null>(null);
  const [selectedGameLoading, setSelectedGameLoading] = useState(false);
  const [aiStatus, setAIStatus] = useState<AIStatus | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [startupError, setStartupError] = useState<string | null>(null);
  const [startupLoading, setStartupLoading] = useState(false);
  const lastHandledUrl = useRef<string | null>(null);

  useEffect(() => {
    ensureLocalUser();
    refreshBackendHealth();
    refreshAIStatus();
  }, []);

  useEffect(() => {
    Linking.getInitialURL()
      .then(handleIncomingUrl)
      .catch(() => {
        // Deep links are best-effort; normal launch should continue.
      });
    const subscription = Linking.addEventListener("url", ({ url }) => handleIncomingUrl(url));
    return () => subscription.remove();
  }, [user?.id]);

  useEffect(() => {
    if (!user) return;
    refreshGames(user.id);
  }, [user?.id]);

  useEffect(() => {
    if (user && pendingInviteCode) setScreen("invites");
  }, [user?.id, pendingInviteCode]);

  useEffect(() => {
    if (!selectedGame) return;
    const interval = setInterval(async () => {
      try {
        if (!user) return;
        const latest = await getGame(selectedGame.id);
        setSelectedGame(latest);
        setSelectedRound(latest.latest_round);
        routeForGame(latest, false);
      } catch {
        // Keep the current UI if the network blips.
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [selectedGame?.id, user?.id, screen]);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") {
        refreshBackendHealth();
        refreshAIStatus();
        if (user) refreshGames(user.id);
        if (selectedGame && user) refreshSelectedGame(selectedGame.id, user.id);
      }
    });
    return () => subscription.remove();
  }, [user?.id, selectedGame?.id]);

  const handleGameEvents = useCallback(() => {
    if (selectedGame && user) refreshSelectedGame(selectedGame.id, user.id);
  }, [selectedGame?.id, user?.id]);

  const openGameById = useCallback(
    async (gameId: string) => {
      if (!user) return;
      try {
        const game = await getGame(gameId);
        openGame(game);
      } catch (error) {
        Alert.alert("Could not open game", getErrorMessage(error));
      }
    },
    [user?.id],
  );

  const realtimeStatus = useGameEvents({
    gameId: selectedGame?.id ?? null,
    enabled: Boolean(selectedGame && user),
    onEvents: handleGameEvents,
  });
  const pushStatus = usePushNotifications(user?.id ?? null, openGameById);

  const showHeader = screen !== "onboarding" && screen !== "profile_setup";
  const showBack = Boolean(user && screen !== "home");
  const selectedLatestRound = useMemo(() => selectedRound ?? selectedGame?.latest_round ?? null, [selectedGame, selectedRound]);

  async function ensureLocalUser() {
    setStartupLoading(true);
    setStartupError(null);
    let onboardingDone: string | null = null;
    let storedId: string | null = null;
    let storedToken: string | null = null;
    try {
      [storedId, storedToken, onboardingDone] = await Promise.all([
        AsyncStorage.getItem(USER_ID_KEY),
        AsyncStorage.getItem(SESSION_TOKEN_KEY),
        AsyncStorage.getItem(ONBOARDING_KEY),
      ]);
    } catch (error) {
      setStartupError(getErrorMessage(error));
      setScreen("startup_error");
      setStartupLoading(false);
      return;
    }

    if (decideSessionBootstrap(Boolean(storedId), Boolean(storedToken)) === "reonboard") {
      if (storedId || storedToken) await clearStoredSession();
      setScreen(onboardingDone ? "profile_setup" : "onboarding");
      setStartupLoading(false);
      return;
    }

    configureApiCredential(storedToken);
    try {
      const existing = await getUser(storedId!);
      setUser(existing);
    } catch (error) {
      const failure = isUnauthorizedError(error) ? "unauthorized" : "transient";
      if (decideSessionBootstrap(true, true, failure) === "reonboard") {
        await clearStoredSession();
        setScreen(onboardingDone ? "profile_setup" : "onboarding");
        setStartupLoading(false);
        return;
      }
      setStartupError(getErrorMessage(error));
      setScreen("startup_error");
    }
    setStartupLoading(false);
  }

  async function clearStoredSession() {
    configureApiCredential(null);
    await Promise.all([
      AsyncStorage.removeItem(USER_ID_KEY),
      AsyncStorage.removeItem(SESSION_TOKEN_KEY),
    ]);
  }

  async function refreshBackendHealth() {
    try {
      const result = await healthCheck();
      setBackendHealth({ status: result.status === "ok" ? "ok" : "unknown", message: result.status });
    } catch (error) {
      captureError(error, { area: "backend_health" });
      setBackendHealth({ status: "unreachable", message: error instanceof Error ? error.message : "Backend is unreachable" });
    }
  }

  async function refreshAIStatus() {
    try {
      setAIStatus(await getAIStatus());
    } catch (error) {
      captureError(error, { area: "ai_status" });
    }
  }

  function handleIncomingUrl(url: string | null) {
    if (!url || lastHandledUrl.current === url) return;
    lastHandledUrl.current = url;
    const inviteCode = parseInviteCodeFromUrl(url);
    if (!inviteCode) return;
    captureMessage("Invite deep link received", { area: "deep_link" });
    setPendingInviteCode(inviteCode);
    if (user) {
      setSelectedGame(null);
      setSelectedRound(null);
      setScreen("invites");
    }
  }

  async function refreshGames(userId: string) {
    setRefreshing(true);
    try {
      setGames(await listGames(userId));
    } catch (error) {
      captureError(error, { area: "games_refresh", userId });
      Alert.alert("Could not load games", getErrorMessage(error));
    } finally {
      setRefreshing(false);
    }
  }

  async function refreshSelectedGame(gameId: string, userId: string) {
    setSelectedGameLoading(true);
    setSelectedGameError(null);
    try {
      const latest = await getGame(gameId);
      setSelectedGame(latest);
      setSelectedRound(latest.latest_round);
      refreshStats(gameId, userId);
      routeForGame(latest, false);
      captureMessage("Selected game refreshed", { area: "navigation", gameId, target: screen });
    } catch (error) {
      captureError(error, { area: "selected_game_refresh", gameId, userId });
      setSelectedGameError(getErrorMessage(error));
      setScreen("waiting");
    } finally {
      setSelectedGameLoading(false);
    }
  }

  async function refreshStats(gameId: string, userId: string) {
    try {
      setSelectedStats(await getGameStats(gameId));
    } catch {
      setSelectedStats(null);
    }
  }

  function openGame(game: Game) {
    setSelectedGame(game);
    setSelectedRound(game.latest_round);
    if (user) refreshStats(game.id, user.id);
    routeForGame(game, true);
  }

  function routeForGame(game: Game, force: boolean) {
    if (!user) return;
    const latest = game.latest_round;
    if (!latest || latest.status === "guessed") {
      if (game.current_turn_user_id === user.id) setScreen("create_round");
      else setScreen(force ? "waiting" : screen);
      return;
    }
    if (latest.status === "failed") {
      setScreen("waiting");
      return;
    }
    if (latest.status === "generating") {
      setScreen("waiting");
      return;
    }
    if (latest.status === "ready_to_guess") {
      setScreen(latest.guesser_user_id === user.id ? "guess" : "waiting");
    }
  }

  async function handleInviteJoined(game: Game) {
    setPendingInviteCode(null);
    if (!user) return;
    captureMessage("Invite join response", {
      area: "invite_join",
      gameId: game.id,
      currentTurnUserId: game.current_turn_user_id,
      latestRoundId: game.latest_round?.id ?? null,
    });
    setSelectedGameLoading(true);
    setSelectedGameError(null);
    try {
      const [joinedGame, refreshedGames] = await Promise.all([getGame(game.id), listGames(user.id)]);
      captureMessage("Games refreshed after invite join", { area: "invite_join", gameId: game.id, count: refreshedGames.length });
      setGames(refreshedGames);
      setSelectedGame(joinedGame);
      setSelectedRound(joinedGame.latest_round);
      routeForGame(joinedGame, true);
      captureMessage("Navigation after invite join", {
        area: "invite_join",
        gameId: joinedGame.id,
        hasRound: Boolean(joinedGame.latest_round),
        currentTurnUserId: joinedGame.current_turn_user_id,
      });
    } catch (error) {
      captureError(error, { area: "invite_join_fetch_game", gameId: game.id, userId: user.id });
      setSelectedGame(game);
      setSelectedRound(game.latest_round);
      setSelectedGameError(getErrorMessage(error));
      setScreen("waiting");
      refreshGames(user.id);
    } finally {
      setSelectedGameLoading(false);
    }
  }

  function handleRoundCreated(round: Round) {
    setSelectedRound(round);
    setSelectedGame((game) => (game ? { ...game, latest_round: round } : game));
    setScreen("waiting");
  }

  function handleRoundRetry(round: Round) {
    setSelectedRound(round);
    setSelectedGame((game) => (game ? { ...game, latest_round: round } : game));
    setScreen("waiting");
  }

  function handleGuessResult(result: GuessResult) {
    if (!selectedRound) return;
    const updatedRound: Round = { ...selectedRound, status: "guessed", guess: result, completed_at: result.created_at };
    setSelectedRound(updatedRound);
    setSelectedGame((game) => (game ? { ...game, latest_round: updatedRound, current_turn_user_id: user?.id ?? game.current_turn_user_id } : game));
    if (selectedGame && user) refreshStats(selectedGame.id, user.id);
    setScreen("result");
  }

  function goHome() {
    if (user) refreshGames(user.id);
    setSelectedGame(null);
    setSelectedRound(null);
    setSelectedStats(null);
    setSelectedGameError(null);
    setScreen("home");
  }

  function goBack() {
    if (screen === "invites" || screen === "edit_profile" || screen === "debug") {
      setScreen("home");
      return;
    }
    goHome();
  }

  async function completeOnboarding() {
    await AsyncStorage.setItem(ONBOARDING_KEY, "1");
    setScreen(user ? (pendingInviteCode ? "invites" : "home") : "profile_setup");
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="dark" />
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.shell}>
        {showHeader && <Header showBack={showBack} onHome={goHome} onBack={goBack} />}
        {screen === "onboarding" && <OnboardingScreen onDone={completeOnboarding} />}
        {screen === "profile_setup" && (
          <ProfileScreen
            user={null}
            onSave={async (payload) => {
              const session = await createUser(payload.display_name, payload.avatar_emoji, payload.avatar_color);
              await Promise.all([
                AsyncStorage.setItem(USER_ID_KEY, session.user.id),
                AsyncStorage.setItem(SESSION_TOKEN_KEY, session.access_token),
              ]);
              configureApiCredential(session.access_token);
              setUser(session.user);
              setScreen(pendingInviteCode ? "invites" : "home");
            }}
          />
        )}
        {screen === "startup_error" && (
          <GamePendingScreen
            game={null}
            loading={startupLoading}
            error={startupError || "The backend is unavailable. Your saved session is still on this device."}
            errorTitle="Could not restore your session"
            onRetry={ensureLocalUser}
            onHome={ensureLocalUser}
          />
        )}
        {user && screen === "edit_profile" && (
          <ProfileScreen
            user={user}
            onCancel={() => setScreen("home")}
            onSave={async (payload) => {
              const updated = await updateUser(user.id, payload);
              setUser(updated);
              setScreen("home");
            }}
          />
        )}
        {user && screen === "home" && (
          <HomeScreen
            user={user}
            games={games}
            backendHealth={backendHealth}
            refreshing={refreshing}
            onRefresh={() => {
              refreshBackendHealth();
              refreshGames(user.id);
            }}
            onEditProfile={() => setScreen("edit_profile")}
            onCreateGame={() => setScreen("invites")}
            onOpenGame={openGame}
            onOpenDebug={() => setScreen("debug")}
          />
        )}
        {user && screen === "debug" && (
          <DebugScreen
            user={user}
            selectedGameId={selectedGame?.id ?? null}
            selectedRound={selectedLatestRound}
            diagnostics={appDiagnostics()}
            backendHealth={backendHealth}
            onRefreshBackendHealth={refreshBackendHealth}
            aiStatus={aiStatus}
            info={{
              realtimeConnected: realtimeStatus.connected,
              fallbackPolling: realtimeStatus.fallbackPolling,
              lastEventId: realtimeStatus.lastEventId,
              lastEventType: realtimeStatus.lastEventType,
              pushPermissionStatus: pushStatus.permissionStatus,
              pushToken: pushStatus.registeredToken,
              pushError: pushStatus.registrationError,
              refreshPushRegistration: pushStatus.refreshRegistration,
            }}
          />
        )}
        {user && screen === "invites" && (
          <InviteScreen
            userId={user.id}
            initialCode={pendingInviteCode}
            onInitialCodeHandled={() => setPendingInviteCode(null)}
            onJoined={handleInviteJoined}
          />
        )}
        {user && screen === "waiting" && selectedGame && !selectedLatestRound && (
          <GamePendingScreen
            game={selectedGame}
            loading={selectedGameLoading}
            error={selectedGameError}
            onRetry={() => refreshSelectedGame(selectedGame.id, user.id)}
            onHome={goHome}
          />
        )}
        {user && screen === "waiting" && !selectedGame && (
          <GamePendingScreen game={null} loading={selectedGameLoading} error={selectedGameError || "No game is selected."} onRetry={goHome} onHome={goHome} />
        )}
        {user && selectedGame && screen === "create_round" && <CreateRoundScreen game={selectedGame} userId={user.id} onCreated={handleRoundCreated} />}
        {user && selectedLatestRound && screen === "waiting" && (
          <WaitingScreen
            round={selectedLatestRound}
            userId={user.id}
            onRetry={handleRoundRetry}
            onContinue={() => setScreen("guess")}
          />
        )}
        {user && selectedLatestRound && selectedGame && screen === "guess" && <GuessScreen round={selectedLatestRound} gameId={selectedGame.id} userId={user.id} onResult={handleGuessResult} />}
        {selectedLatestRound && screen === "result" && (
          <ResultScreen
            round={selectedLatestRound}
            canCreateNext={Boolean(user && selectedGame?.current_turn_user_id === user.id)}
            onNext={() => setScreen("create_round")}
            stats={selectedStats}
            userId={user?.id}
          />
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Unknown error";
}
