import AsyncStorage from "@react-native-async-storage/async-storage";
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, AppState, type AppStateStatus, KeyboardAvoidingView, Linking, Platform, SafeAreaView } from "react-native";

import { ApiError, configureApiCredential, healthCheck, isUnauthorizedError } from "./src/api/client";
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
import { parseAppLink } from "./src/utils/deepLinks";
import { captureError, captureMessage } from "./src/utils/errorReporter";
import { decideSessionBootstrap, restoredSessionDestination } from "./src/sessionBootstrap";
import { createSessionEpoch } from "./src/sessionEpoch";
import { createRequestScope } from "./src/requestScope";
import { createLatestTargetCoordinator, type LatestTargetCoordinator } from "./src/latestTargetCoordinator";
import { createLatestOperation } from "./src/latestOperation";
import { createActionContextGuard, isActionContextCurrent, type ActionContext } from "./src/actionContext";
import { retireGameOpenState, type GameOpenRetirementMode } from "./src/gameOpenState";
import { decideGameRoute, type GameScreen } from "./src/roundLifecycle";

type Screen = GameScreen;

const USER_ID_KEY = "ai-pictionary:user-id";
const SESSION_TOKEN_KEY = "ai-pictionary:session-token";
const ONBOARDING_KEY = "ai-pictionary:onboarding-complete";

type GameOpenTarget = { gameId: string; userId: string; sessionEpoch: number };

export default function App() {
  const [screen, setScreen] = useState<Screen>("home");
  const [user, setUser] = useState<User | null>(null);
  const [games, setGames] = useState<Game[]>([]);
  const [selectedGame, setSelectedGame] = useState<Game | null>(null);
  const [selectedRound, setSelectedRound] = useState<Round | null>(null);
  const [selectedStats, setSelectedStats] = useState<GameStats | null>(null);
  const [pendingInviteCode, setPendingInviteCode] = useState<string | null>(null);
  const [pendingGameId, setPendingGameId] = useState<string | null>(null);
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
  const [sessionRetiring, setSessionRetiring] = useState(false);
  const [sessionAccessToken, setSessionAccessToken] = useState<string | null>(null);
  const [appState, setAppState] = useState<AppStateStatus>(AppState.currentState);
  const [openingGameId, setOpeningGameId] = useState<string | null>(null);
  const [actionLifecycleEpoch, setActionLifecycleEpoch] = useState(0);
  const sessionEpoch = useRef(createSessionEpoch()).current;
  const identityRequests = useRef(createRequestScope()).current;
  const gameRequests = useRef(createRequestScope()).current;
  const userRef = useRef<User | null>(null);
  const selectedGameRef = useRef<Game | null>(null);
  const selectedRoundRef = useRef<Round | null>(null);
  const screenRef = useRef<Screen>(screen);
  const pendingGameRef = useRef<string | null>(null);
  const openingGameRef = useRef<string | null>(null);
  const mountedRef = useRef(true);
  const gamesRefreshGeneration = useRef(0);
  const statsRefreshGeneration = useRef(0);
  const actionLifecycleEpochRef = useRef(0);
  const gameOpenRetirementGenerationRef = useRef(0);
  const observedGuessRoundIdRef = useRef<string | null>(null);
  const selectedRefreshOperation = useRef(createLatestOperation(setSelectedGameLoading)).current;
  const gameOpenCoordinatorRef = useRef<LatestTargetCoordinator<GameOpenTarget, Game> | null>(null);
  userRef.current = user;
  selectedGameRef.current = selectedGame;
  selectedRoundRef.current = selectedRound;
  screenRef.current = screen;
  pendingGameRef.current = pendingGameId;
  const appIsActive = appState === "active";
  const renderedActionContext: ActionContext = {
    epoch: actionLifecycleEpoch,
    userId: user?.id ?? null,
    gameId: selectedGame?.id ?? null,
    roundId: selectedRound?.id ?? selectedGame?.latest_round?.id ?? null,
  };

  if (!gameOpenCoordinatorRef.current) {
    gameOpenCoordinatorRef.current = createLatestTargetCoordinator<GameOpenTarget, Game>({
      key: (target) => `${target.sessionEpoch}:${target.userId}:${target.gameId}`,
      run: async (target, signal) => {
        retireActionWork();
        retireGameWork();
        return getGame(target.gameId, signal);
      },
      accept: (target, game) => {
        if (!isGameOpenTargetCurrent(target)) return;
        clearGameOpenState(target.gameId);
        openGame(game);
      },
      reject: (target, error) => {
        if (!isGameOpenTargetCurrent(target)) return;
        clearGameOpenState(target.gameId);
        Alert.alert("Could not open game", friendlyGameLinkError(error));
      },
    });
  }

  useEffect(() => {
    ensureLocalUser();
    refreshBackendHealth();
    refreshAIStatus();
    return () => {
      mountedRef.current = false;
      identityRequests.retire();
      gameRequests.retire();
      selectedRefreshOperation.retire();
      retireGameOpenWork("clear-pending");
    };
  }, []);

  useEffect(() => {
    Linking.getInitialURL()
      .then(handleIncomingUrl)
      .catch(() => {
        // Deep links are best-effort; normal launch should continue.
      });
    const subscription = Linking.addEventListener("url", ({ url }) => handleIncomingUrl(url));
    return () => subscription.remove();
  }, []);

  useEffect(() => {
    if (!user || !appIsActive) {
      identityRequests.retire();
      return;
    }
    identityRequests.activate(user.id);
    refreshGames(user.id);
  }, [user?.id, appIsActive]);

  useEffect(() => {
    if (!selectedGame || !user || !appIsActive) {
      gameRequests.retire();
      selectedRefreshOperation.retire();
      return;
    }
    gameRequests.activate(gameScopeKey(user.id, selectedGame.id));
  }, [selectedGame?.id, user?.id, appIsActive]);

  useEffect(() => {
    if (user && pendingInviteCode) setScreen("invites");
  }, [user?.id, pendingInviteCode]);

  useEffect(() => {
    if (!user || !pendingGameId || !appIsActive) return;
    void openGameById(pendingGameId);
  }, [user?.id, pendingGameId, appIsActive]);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      setAppState(state);
      if (state === "active") {
        refreshBackendHealth();
        refreshAIStatus();
        const activeUser = userRef.current;
        const activeGame = selectedGameRef.current;
        if (!activeUser) {
          void ensureLocalUser();
        }
        if (activeGame && activeUser) {
          gameRequests.activate(gameScopeKey(activeUser.id, activeGame.id));
          refreshSelectedGame(activeGame.id, activeUser.id);
        }
      } else {
        identityRequests.retire();
        gameRequests.retire();
        selectedRefreshOperation.retire();
        retireGameOpenWork("preserve-pending");
        retireActionWork();
      }
    });
    return () => subscription.remove();
  }, []);

  const handleGameEvents = useCallback((events: { game_id: string }[]) => {
    const activeGame = selectedGameRef.current;
    const activeUser = userRef.current;
    if (!activeGame || !activeUser || events.some((event) => event.game_id !== activeGame.id)) return;
    void refreshSelectedGame(activeGame.id, activeUser.id);
  }, []);

  const openGameById = useCallback(
    async (gameId: string) => {
      const activeUser = userRef.current;
      if (!activeUser) return;
      if (AppState.currentState !== "active") {
        queuePendingGame(gameId);
        return;
      }
      queuePendingGame(gameId);
      openingGameRef.current = gameId;
      setOpeningGameId(gameId);
      const retirementGeneration = gameOpenRetirementGenerationRef.current;
      await gameOpenCoordinatorRef.current?.request({
        gameId,
        userId: activeUser.id,
        sessionEpoch: sessionEpoch.capture(),
      });
      if (retirementGeneration !== gameOpenRetirementGenerationRef.current) return;
      if (openingGameRef.current === gameId) clearGameOpenState(gameId);
    },
    [],
  );

  const realtimeStatus = useGameEvents({
    gameId: selectedGame?.id ?? null,
    userId: user?.id ?? null,
    enabled: Boolean(selectedGame && user && !sessionRetiring && appIsActive),
    onEvents: handleGameEvents,
  });
  const pushStatus = usePushNotifications(user?.id ?? null, sessionAccessToken, openGameById, !sessionRetiring);

  const showHeader = screen !== "onboarding" && screen !== "profile_setup";
  const showBack = Boolean(user && screen !== "home");
  const selectedLatestRound = useMemo(() => selectedRound ?? selectedGame?.latest_round ?? null, [selectedGame, selectedRound]);

  async function ensureLocalUser() {
    const capturedEpoch = sessionEpoch.capture();
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
      if (!sessionEpoch.isCurrent(capturedEpoch)) return;
    } catch (error) {
      if (!sessionEpoch.isCurrent(capturedEpoch)) return;
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
    identityRequests.activate(storedId!);
    const request = identityRequests.begin(storedId!);
    try {
      const existing = await getUser(storedId!, request.signal);
      if (!sessionEpoch.isCurrent(capturedEpoch) || !request.isCurrent()) return;
      sessionEpoch.activate();
      identityRequests.activate(existing.id);
      userRef.current = existing;
      setSessionAccessToken(storedToken);
      setUser(existing);
      setStartupError(null);
      setScreen(restoredSessionDestination(Boolean(pendingInviteCode)));
    } catch (error) {
      if (!sessionEpoch.isCurrent(capturedEpoch) || !request.isCurrent()) return;
      const failure = isUnauthorizedError(error) ? "unauthorized" : "transient";
      if (decideSessionBootstrap(true, true, failure) === "reonboard") {
        await clearStoredSession();
        setScreen(onboardingDone ? "profile_setup" : "onboarding");
        setStartupLoading(false);
        return;
      }
      setStartupError(getErrorMessage(error));
      setScreen("startup_error");
    } finally {
      request.finish();
    }
    setStartupLoading(false);
  }

  async function clearStoredSession() {
    configureApiCredential(null);
    setSessionAccessToken(null);
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
    const link = parseAppLink(url);
    if (!link) return;
    captureMessage("App deep link received", { area: "deep_link", kind: link.kind });
    if (link.kind === "invite") {
      retireGameOpenWork("clear-pending");
      setPendingInviteCode(link.code);
      if (userRef.current) {
        retireActionWork();
        retireGameWork();
        selectedGameRef.current = null;
        selectedRoundRef.current = null;
        setSelectedGame(null);
        setSelectedRound(null);
        setScreen("invites");
      }
    } else {
      setPendingInviteCode(null);
      if (userRef.current && AppState.currentState === "active") void openGameById(link.gameId);
      else queuePendingGame(link.gameId);
    }
  }

  async function refreshGames(userId: string) {
    if (AppState.currentState !== "active") return;
    const capturedEpoch = sessionEpoch.capture();
    const generation = ++gamesRefreshGeneration.current;
    identityRequests.activate(userId);
    const request = identityRequests.begin(userId);
    setRefreshing(true);
    try {
      const refreshedGames = await listGames(userId, request.signal);
      if (request.isCurrent() && generation === gamesRefreshGeneration.current) sessionEpoch.runIfCurrent(capturedEpoch, () => setGames(refreshedGames));
    } catch (error) {
      if (request.isCurrent() && generation === gamesRefreshGeneration.current) sessionEpoch.runIfCurrent(capturedEpoch, () => {
        captureError(error, { area: "games_refresh", userId });
        Alert.alert("Could not load games", getErrorMessage(error));
      });
    } finally {
      if (generation === gamesRefreshGeneration.current) {
        request.runIfCurrent(() => sessionEpoch.runIfCurrent(capturedEpoch, () => setRefreshing(false)));
      }
      request.finish();
    }
  }

  async function refreshSelectedGame(gameId: string, userId: string) {
    if (AppState.currentState !== "active") return;
    const capturedEpoch = sessionEpoch.capture();
    const key = gameScopeKey(userId, gameId);
    const request = selectedRefreshOperation.begin(key);
    setSelectedGameError(null);
    try {
      const latest = await getGame(gameId, request.signal);
      if (!sessionEpoch.isCurrent(capturedEpoch) || !request.isCurrent()) return;
      if (selectedGameRef.current?.id !== gameId || userRef.current?.id !== userId) return;
      selectedGameRef.current = latest;
      selectedRoundRef.current = latest.latest_round;
      setSelectedGame(latest);
      setSelectedRound(latest.latest_round);
      void refreshStats(gameId, userId);
      routeForGame(latest, false);
      captureMessage("Selected game refreshed", { area: "navigation", gameId, target: screenRef.current });
    } catch (error) {
      if (!sessionEpoch.isCurrent(capturedEpoch) || !request.isCurrent()) return;
      captureError(error, { area: "selected_game_refresh", gameId, userId });
      setSelectedGameError(getErrorMessage(error));
      setScreen("waiting");
    } finally {
      request.settle();
    }
  }

  async function refreshStats(gameId: string, userId: string) {
    if (AppState.currentState !== "active") return;
    const capturedEpoch = sessionEpoch.capture();
    const generation = ++statsRefreshGeneration.current;
    const request = gameRequests.begin(gameScopeKey(userId, gameId));
    try {
      const stats = await getGameStats(gameId, request.signal);
      if (generation === statsRefreshGeneration.current) request.runIfCurrent(() => sessionEpoch.runIfCurrent(capturedEpoch, () => setSelectedStats(stats)));
    } catch {
      if (generation === statsRefreshGeneration.current) request.runIfCurrent(() => sessionEpoch.runIfCurrent(capturedEpoch, () => setSelectedStats(null)));
    } finally {
      request.finish();
    }
  }

  function openGame(game: Game) {
    const activeUser = userRef.current;
    if (!activeUser) return;
    retireGameWork();
    observedGuessRoundIdRef.current = null;
    gameRequests.activate(gameScopeKey(activeUser.id, game.id));
    selectedGameRef.current = game;
    selectedRoundRef.current = game.latest_round;
    setSelectedGame(game);
    setSelectedRound(game.latest_round);
    setSelectedStats(null);
    setSelectedGameError(null);
    void refreshStats(game.id, activeUser.id);
    routeForGame(game, true);
  }

  function routeForGame(game: Game, force: boolean) {
    const activeUser = userRef.current;
    if (!activeUser) return;
    const decision = decideGameRoute({
      latestRound: game.latest_round,
      currentTurnUserId: game.current_turn_user_id,
      userId: activeUser.id,
      currentScreen: screenRef.current,
      force,
      observedGuessRoundId: observedGuessRoundIdRef.current,
    });
    observedGuessRoundIdRef.current = decision.observedGuessRoundId;
    setScreen(decision.screen);
  }

  async function handleLocalStateReset() {
    await retireSessionAndResetClient(true);
  }

  async function handleBackendDataReset() {
    await retireSessionAndResetClient(false);
  }

  async function retireSessionAndResetClient(unregisterPush: boolean) {
    sessionEpoch.retire();
    identityRequests.retire();
    retireGameOpenWork("clear-pending");
    retireActionWork();
    retireGameWork();
    userRef.current = null;
    selectedGameRef.current = null;
    selectedRoundRef.current = null;
    setSessionRetiring(true);
    let resetError: unknown = null;
    try {
      if (unregisterPush) {
        try {
          await pushStatus.unregisterCurrentToken();
        } catch (error) {
          captureError(error, { area: "push_unregistration_during_reset", userId: user?.id ?? null });
        }
      }
      try {
        await clearStoredSession();
        await AsyncStorage.removeItem(ONBOARDING_KEY);
      } catch (error) {
        resetError = error;
      }
    } finally {
      // Local state is retired even when best-effort push or storage cleanup fails.
      configureApiCredential(null);
      setSessionAccessToken(null);
      setUser(null);
      selectedGameRef.current = null;
      selectedRoundRef.current = null;
      observedGuessRoundIdRef.current = null;
      setSelectedGame(null);
      setSelectedRound(null);
      setSelectedStats(null);
      setGames([]);
      setPendingInviteCode(null);
      pendingGameRef.current = null;
      setPendingGameId(null);
      setSelectedGameError(null);
      setSelectedGameLoading(false);
      setRefreshing(false);
      setStartupLoading(false);
      setStartupError(null);
      openingGameRef.current = null;
      setOpeningGameId(null);
      setScreen("onboarding");
      setSessionRetiring(false);
    }
    if (resetError) throw resetError;
  }

  async function handleInviteJoined(capturedContext: ActionContext, game: Game) {
    if (!actionContextIsCurrent(capturedContext)) return;
    const capturedEpoch = sessionEpoch.capture();
    setPendingInviteCode(null);
    const activeUser = userRef.current;
    if (!activeUser) return;
    const request = selectedRefreshOperation.begin(gameScopeKey(activeUser.id, game.id));
    captureMessage("Invite join response", {
      area: "invite_join",
      gameId: game.id,
      currentTurnUserId: game.current_turn_user_id,
      latestRoundId: game.latest_round?.id ?? null,
    });
    setSelectedGameError(null);
    try {
      const [joinedGame, refreshedGames] = await Promise.all([getGame(game.id, request.signal), listGames(activeUser.id, request.signal)]);
      if (!sessionEpoch.isCurrent(capturedEpoch) || !request.isCurrent() || !actionContextIsCurrent(capturedContext)) return;
      captureMessage("Games refreshed after invite join", { area: "invite_join", gameId: game.id, count: refreshedGames.length });
      setGames(refreshedGames);
      openGame(joinedGame);
      captureMessage("Navigation after invite join", {
        area: "invite_join",
        gameId: joinedGame.id,
        hasRound: Boolean(joinedGame.latest_round),
        currentTurnUserId: joinedGame.current_turn_user_id,
      });
    } catch (error) {
      if (!sessionEpoch.isCurrent(capturedEpoch) || !request.isCurrent() || !actionContextIsCurrent(capturedContext)) return;
      captureError(error, { area: "invite_join_fetch_game", gameId: game.id, userId: activeUser.id });
      openGame(game);
      setSelectedGameError(getErrorMessage(error));
      setScreen("waiting");
      refreshGames(activeUser.id);
    } finally {
      request.settle();
    }
  }

  function handleRoundCreated(round: Round, capturedContext: ActionContext) {
    if (!actionContextIsCurrent(capturedContext) || round.game_id !== capturedContext.gameId) return;
    selectedRoundRef.current = round;
    observedGuessRoundIdRef.current = null;
    setSelectedRound(round);
    setSelectedGame((game) => (game ? { ...game, latest_round: round } : game));
    setScreen("waiting");
  }

  function handleRoundRetry(round: Round, capturedContext: ActionContext) {
    if (!actionContextIsCurrent(capturedContext) || round.id !== capturedContext.roundId || round.game_id !== capturedContext.gameId) return;
    selectedRoundRef.current = round;
    setSelectedRound(round);
    setSelectedGame((game) => (game ? { ...game, latest_round: round } : game));
    setScreen("waiting");
  }

  function handleGuessResult(result: GuessResult, capturedContext: ActionContext) {
    const activeRound = selectedRoundRef.current;
    const activeGame = selectedGameRef.current;
    const activeUser = userRef.current;
    if (!activeRound || !activeGame || !activeUser || !actionContextIsCurrent(capturedContext) || result.round_id !== capturedContext.roundId) return;
    const updatedRound: Round = { ...activeRound, status: "guessed", guess: result, completed_at: result.created_at };
    observedGuessRoundIdRef.current = activeRound.id;
    selectedRoundRef.current = updatedRound;
    setSelectedRound(updatedRound);
    setSelectedGame((game) => (game ? { ...game, latest_round: updatedRound, current_turn_user_id: activeUser.id } : game));
    void refreshStats(activeGame.id, activeUser.id);
    setScreen("result");
  }

  function goHome() {
    if (user) refreshGames(user.id);
    retireGameOpenWork("clear-pending");
    retireActionWork();
    retireGameWork();
    selectedGameRef.current = null;
    selectedRoundRef.current = null;
    observedGuessRoundIdRef.current = null;
    setSelectedGame(null);
    setSelectedRound(null);
    setSelectedStats(null);
    setSelectedGameError(null);
    setScreen("home");
  }

  function goBack() {
    if (screen === "invites" || screen === "edit_profile" || screen === "debug") {
      goHome();
      return;
    }
    goHome();
  }

  function goToNextRound() {
    observedGuessRoundIdRef.current = null;
    setScreen("create_round");
  }

  async function completeOnboarding() {
    await AsyncStorage.setItem(ONBOARDING_KEY, "1");
    setScreen(user ? (pendingInviteCode ? "invites" : "home") : "profile_setup");
  }

  function retireActionWork() {
    const nextEpoch = actionLifecycleEpochRef.current + 1;
    actionLifecycleEpochRef.current = nextEpoch;
    if (mountedRef.current) setActionLifecycleEpoch(nextEpoch);
  }

  function retireGameWork() {
    gameRequests.retire();
    selectedRefreshOperation.retire();
    statsRefreshGeneration.current += 1;
  }

  function currentActionContext(): ActionContext {
    return {
      epoch: actionLifecycleEpochRef.current,
      userId: userRef.current?.id ?? null,
      gameId: selectedGameRef.current?.id ?? null,
      roundId: selectedRoundRef.current?.id ?? selectedGameRef.current?.latest_round?.id ?? null,
    };
  }

  function actionContextIsCurrent(capturedContext: ActionContext) {
    return isActionContextCurrent(capturedContext, currentActionContext(), AppState.currentState === "active");
  }

  function isGameOpenTargetCurrent(target: GameOpenTarget) {
    return (
      AppState.currentState === "active" &&
      userRef.current?.id === target.userId &&
      sessionEpoch.isCurrent(target.sessionEpoch)
    );
  }

  function queuePendingGame(gameId: string) {
    pendingGameRef.current = gameId;
    if (mountedRef.current) setPendingGameId(gameId);
  }

  function retireGameOpenWork(mode: GameOpenRetirementMode) {
    gameOpenRetirementGenerationRef.current += 1;
    gameOpenCoordinatorRef.current?.retire();
    const next = retireGameOpenState(
      { pendingGameId: pendingGameRef.current, openingGameId: openingGameRef.current },
      mode,
    );
    pendingGameRef.current = next.pendingGameId;
    openingGameRef.current = next.openingGameId;
    if (!mountedRef.current) return;
    setPendingGameId(next.pendingGameId);
    setOpeningGameId(next.openingGameId);
  }

  function clearGameOpenState(gameId: string) {
    if (pendingGameRef.current === gameId) {
      pendingGameRef.current = null;
      if (mountedRef.current) setPendingGameId(null);
    }
    if (openingGameRef.current === gameId) {
      openingGameRef.current = null;
      if (mountedRef.current) setOpeningGameId(null);
    }
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
            lifecycleEpoch={actionLifecycleEpoch}
            onSave={async (payload, signal) => {
              const profileActionIsCurrent = createActionContextGuard(
                renderedActionContext,
                currentActionContext,
                () => AppState.currentState === "active",
              );
              if (!profileActionIsCurrent(signal)) return;
              const session = await createUser(payload.display_name, payload.avatar_emoji, payload.avatar_color, signal);
              if (!profileActionIsCurrent(signal)) return;
              await Promise.all([
                AsyncStorage.setItem(USER_ID_KEY, session.user.id),
                AsyncStorage.setItem(SESSION_TOKEN_KEY, session.access_token),
              ]);
              if (!profileActionIsCurrent(signal)) return;
              configureApiCredential(session.access_token);
              sessionEpoch.activate();
              identityRequests.activate(session.user.id);
              userRef.current = session.user;
              setSessionAccessToken(session.access_token);
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
            lifecycleEpoch={actionLifecycleEpoch}
            onCancel={() => {
              goHome();
            }}
            onSave={async (payload, signal) => {
              const profileActionIsCurrent = createActionContextGuard(
                renderedActionContext,
                currentActionContext,
                () => AppState.currentState === "active",
              );
              if (!profileActionIsCurrent(signal)) return;
              const updated = await updateUser(user.id, payload, signal);
              if (!profileActionIsCurrent(signal)) return;
              userRef.current = updated;
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
            onOpenGame={(game) => void openGameById(game.id)}
            openingGameId={openingGameId}
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
            onResetLocalState={handleLocalStateReset}
            onBackendResetComplete={handleBackendDataReset}
            aiStatus={aiStatus}
            lifecycleEpoch={actionLifecycleEpoch}
            info={{
              realtimeConnected: realtimeStatus.connected,
              fallbackPolling: realtimeStatus.fallbackPolling,
              lastEventId: realtimeStatus.lastEventId,
              lastEventType: realtimeStatus.lastEventType,
              pushPermissionStatus: pushStatus.permissionStatus,
              pushRegistered: pushStatus.registered,
              pushTokenFingerprint: pushStatus.tokenFingerprint,
              pushError: pushStatus.registrationError,
              refreshPushRegistration: pushStatus.refreshRegistration,
            }}
          />
        )}
        {user && screen === "invites" && (
          <InviteScreen
            userId={user.id}
            lifecycleEpoch={actionLifecycleEpoch}
            initialCode={pendingInviteCode}
            onInitialCodeHandled={() => setPendingInviteCode(null)}
            onJoined={(game) => handleInviteJoined(renderedActionContext, game)}
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
        {user && selectedGame && screen === "create_round" && (
          <CreateRoundScreen
            game={selectedGame}
            userId={user.id}
            lifecycleEpoch={actionLifecycleEpoch}
            onCreated={(round) => handleRoundCreated(round, renderedActionContext)}
          />
        )}
        {user && selectedLatestRound && screen === "waiting" && (
          <WaitingScreen
            round={selectedLatestRound}
            userId={user.id}
            lifecycleEpoch={actionLifecycleEpoch}
            onRetry={(round) => handleRoundRetry(round, renderedActionContext)}
            onContinue={() => setScreen("guess")}
          />
        )}
        {user && selectedLatestRound && selectedGame && screen === "guess" && (
          <GuessScreen
            round={selectedLatestRound}
            gameId={selectedGame.id}
            userId={user.id}
            lifecycleEpoch={actionLifecycleEpoch}
            onResult={(result) => handleGuessResult(result, renderedActionContext)}
          />
        )}
        {selectedLatestRound && screen === "result" && (
          <ResultScreen
            round={selectedLatestRound}
            canCreateNext={Boolean(user && selectedGame?.current_turn_user_id === user.id)}
            onNext={goToNextRound}
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

function gameScopeKey(userId: string, gameId: string) {
  return `${userId}:${gameId}`;
}

function friendlyGameLinkError(error: unknown) {
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
    return "This game is not available to the current profile.";
  }
  if (error instanceof ApiError && error.status === 404) return "This game no longer exists.";
  return getErrorMessage(error);
}
