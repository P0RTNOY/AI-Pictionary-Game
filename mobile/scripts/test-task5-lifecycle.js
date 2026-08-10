const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

const root = path.resolve(__dirname, "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");

function loadTypeScriptModule(relativePath) {
  const source = read(relativePath);
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const loaded = { exports: {} };
  new Function("exports", "module", compiled)(loaded.exports, loaded);
  return loaded.exports;
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

async function run() {
  const { createRequestScope } = loadTypeScriptModule("src/requestScope.ts");
  const scope = createRequestScope();
  scope.activate("user-a:game-a");
  const oldGame = scope.begin("user-a:game-a");
  assert.equal(oldGame.isCurrent(), true);
  scope.activate("user-a:game-b");
  assert.equal(oldGame.signal.aborted, true, "switching games must abort the old request");
  assert.equal(oldGame.isCurrent(), false, "an old game completion must be rejected");

  const backgrounded = scope.begin("user-a:game-b");
  scope.retire();
  assert.equal(backgrounded.signal.aborted, true, "backgrounding must abort in-flight requests");
  assert.equal(backgrounded.isCurrent(), false);
  scope.activate("user-a:game-b");
  const resumed = scope.begin("user-a:game-b");
  assert.equal(resumed.isCurrent(), true);
  resumed.finish();

  const { createLatestTargetCoordinator } = loadTypeScriptModule("src/latestTargetCoordinator.ts");
  const targetWork = { A: deferred(), B: deferred() };
  const targetSignals = {};
  const acceptedTargets = [];
  const targetCoordinator = createLatestTargetCoordinator({
    key: (target) => target,
    run: (target, signal) => {
      targetSignals[target] = signal;
      return targetWork[target].promise;
    },
    accept: (target) => acceptedTargets.push(target),
    reject: () => {},
    now: () => 0,
  });
  const targetA = targetCoordinator.request("A");
  await Promise.resolve();
  const targetB = targetCoordinator.request("B");
  assert.equal(targetSignals.A.aborted, true, "B must supersede and abort an in-flight A open");
  targetWork.A.resolve("old-a");
  await targetA;
  assert.deepEqual(acceptedTargets, [], "a retired A completion cannot navigate");
  targetWork.B.resolve("latest-b");
  await targetB;
  assert.deepEqual(acceptedTargets, ["B"]);

  let retiredBeforeRunCalls = 0;
  const retireBeforeRun = createLatestTargetCoordinator({
    key: (target) => target,
    run: async () => {
      retiredBeforeRunCalls += 1;
      return "should-not-run";
    },
    accept: () => {},
    reject: () => {},
  });
  const retiredBeforeRunWork = retireBeforeRun.request("A");
  retireBeforeRun.retire();
  await retiredBeforeRunWork;
  assert.equal(retiredBeforeRunCalls, 0, "retiring before the deferred run must prevent the request from starting");

  let retryAttempt = 0;
  const retryAccepted = [];
  const retryCoordinator = createLatestTargetCoordinator({
    key: (target) => target,
    run: async () => {
      retryAttempt += 1;
      if (retryAttempt === 1) throw new Error("transient");
      return "recovered";
    },
    accept: (target) => retryAccepted.push(target),
    reject: () => {},
    now: () => retryAttempt * 10_000,
  });
  await retryCoordinator.request("same-game-url");
  await retryCoordinator.request("same-game-url");
  assert.equal(retryAttempt, 2, "a transient failure must not suppress the same URL forever");
  assert.deepEqual(retryAccepted, ["same-game-url"]);

  const { createLatestOperation } = loadTypeScriptModule("src/latestOperation.ts");
  const loadingStates = [];
  const operation = createLatestOperation((loading) => loadingStates.push(loading));
  const refreshA = operation.begin("user-a:game-a");
  operation.retire();
  assert.equal(refreshA.signal.aborted, true);
  assert.equal(refreshA.isCurrent(), false);
  const refreshB = operation.begin("user-a:game-b");
  refreshA.settle();
  assert.equal(refreshB.isCurrent(), true, "a stale completion cannot settle B's loading state");
  refreshB.settle();
  assert.deepEqual(loadingStates, [true, false, true, false]);

  const { retireGameOpenState } = loadTypeScriptModule("src/gameOpenState.ts");
  const backgroundedOpen = retireGameOpenState(
    { pendingGameId: "game-a", openingGameId: "game-a" },
    "preserve-pending",
  );
  assert.deepEqual(backgroundedOpen, { pendingGameId: "game-a", openingGameId: null });
  let resumedOpenRequests = 0;
  if (backgroundedOpen.pendingGameId) resumedOpenRequests += 1;
  assert.equal(resumedOpenRequests, 1, "resume must retry the game retained during background retirement");
  const homeCancelledOpen = retireGameOpenState(backgroundedOpen, "clear-pending");
  assert.deepEqual(homeCancelledOpen, { pendingGameId: null, openingGameId: null });
  if (homeCancelledOpen.pendingGameId) resumedOpenRequests += 1;
  assert.equal(resumedOpenRequests, 1, "Home must clear and unlock the pending open without re-requesting it");

  const { createActionContextGuard, isActionContextCurrent } = loadTypeScriptModule("src/actionContext.ts");
  const capturedAction = { epoch: 4, userId: "user-a", gameId: "game-a", roundId: "round-a" };
  assert.equal(isActionContextCurrent(capturedAction, capturedAction, true), true);
  assert.equal(
    isActionContextCurrent(capturedAction, { ...capturedAction, epoch: 5, gameId: "game-b" }, true),
    false,
    "an old-game mutation must be rejected after B opens",
  );
  assert.equal(isActionContextCurrent(capturedAction, capturedAction, false), false, "backgrounding retires actions");

  let profileForeground = true;
  let profileWrites = 0;
  const profileSaveResult = deferred();
  const profileSignal = new AbortController().signal;
  const profileActionIsCurrent = createActionContextGuard(
    capturedAction,
    () => capturedAction,
    () => profileForeground,
  );
  const deferredProfileSave = (async () => {
    await profileSaveResult.promise;
    if (profileActionIsCurrent(profileSignal)) profileWrites += 1;
  })();
  profileForeground = false;
  profileSaveResult.resolve();
  await deferredProfileSave;
  assert.equal(profileSignal.aborted, false, "the passive screen cleanup has not aborted yet");
  assert.equal(profileWrites, 0, "a profile save resolving after background must not write state or credentials");

  const { createRealtimeFailurePolicy } = loadTypeScriptModule("src/realtimePolicy.ts");
  const flapPolicy = createRealtimeFailurePolicy(2);
  const fakeSocket = {
    open: () => flapPolicy.opened(),
    close: () => flapPolicy.closed(),
  };
  fakeSocket.open();
  assert.equal(fakeSocket.close().usePolling, false);
  fakeSocket.open();
  assert.equal(fakeSocket.close().usePolling, true, "repeated fake WebSocket flaps must enter polling fallback");
  assert.equal(fakeSocket.open().usePolling, true, "a brief reopen must keep polling active until the socket proves healthy");
  assert.equal(flapPolicy.healthy().usePolling, false);
  assert.equal(flapPolicy.failures(), 0, "only a sustained healthy connection resets failures");

  const { createRealtimeCursor } = loadTypeScriptModule("src/realtimeCursor.ts");
  const realtimeCursor = createRealtimeCursor(3);
  assert.equal(realtimeCursor.setIdentity("game-a", "user-a"), true);
  assert.deepEqual(realtimeCursor.accept("game-a", [
    { id: 1, game_id: "game-a" },
    { id: 2, game_id: "game-a" },
  ]).map((event) => event.id), [1, 2]);
  assert.equal(realtimeCursor.afterId(), 2);
  assert.equal(realtimeCursor.setIdentity("game-a", "user-a"), false, "background disable/enable preserves identity cursor");
  assert.deepEqual(realtimeCursor.accept("game-a", [
    { id: 1, game_id: "game-a" },
    { id: 2, game_id: "game-a" },
    { id: 3, game_id: "game-a" },
  ]).map((event) => event.id), [3], "resume cannot re-emit replayed IDs");
  realtimeCursor.accept("game-a", [
    { id: 4, game_id: "game-a" },
    { id: 5, game_id: "game-a" },
  ]);
  assert.equal(realtimeCursor.seenSize(), 3, "dedupe memory stays bounded");
  assert.equal(realtimeCursor.setIdentity("game-b", "user-a"), true);
  assert.equal(realtimeCursor.afterId(), 0, "game change resets cursor");
  assert.deepEqual(realtimeCursor.accept("game-b", [{ id: 1, game_id: "game-b" }]).map((event) => event.id), [1]);
  assert.equal(realtimeCursor.setIdentity("game-b", "user-b"), true);
  assert.equal(realtimeCursor.afterId(), 0, "user change resets cursor");

  const roundLifecyclePath = path.join(root, "src/roundLifecycle.ts");
  assert.equal(fs.existsSync(roundLifecyclePath), true, "round lifecycle routing must be modeled independently");
  const { decideGameRoute, isGuessInteractionAllowed } = loadTypeScriptModule("src/roundLifecycle.ts");
  const readyRoute = decideGameRoute({
    latestRound: { id: "round-a", status: "ready_to_guess", guesser_user_id: "user-a" },
    currentTurnUserId: "user-b",
    userId: "user-a",
    currentScreen: "waiting",
    force: true,
    observedGuessRoundId: null,
  });
  assert.deepEqual(readyRoute, { screen: "guess", observedGuessRoundId: "round-a" });
  const judgingRoute = decideGameRoute({
    latestRound: { id: "round-a", status: "judging", guesser_user_id: "user-a" },
    currentTurnUserId: "user-b",
    userId: "user-a",
    currentScreen: readyRoute.screen,
    force: false,
    observedGuessRoundId: readyRoute.observedGuessRoundId,
  });
  assert.deepEqual(judgingRoute, { screen: "guess", observedGuessRoundId: "round-a" }, "judging_started must keep the guess request mounted");
  const scoredAfterLostResponse = decideGameRoute({
    latestRound: { id: "round-a", status: "guessed", guesser_user_id: "user-a" },
    currentTurnUserId: "user-a",
    userId: "user-a",
    currentScreen: judgingRoute.screen,
    force: false,
    observedGuessRoundId: judgingRoute.observedGuessRoundId,
  });
  assert.deepEqual(scoredAfterLostResponse, { screen: "result", observedGuessRoundId: "round-a" }, "round.scored refresh must reach Result without the HTTP response");
  const reopenedCompleted = decideGameRoute({
    latestRound: { id: "old-round", status: "guessed", guesser_user_id: "user-a" },
    currentTurnUserId: "user-a",
    userId: "user-a",
    currentScreen: "home",
    force: true,
    observedGuessRoundId: null,
  });
  assert.deepEqual(reopenedCompleted, { screen: "create_round", observedGuessRoundId: null }, "reopening an old completed game must not trap the user on Result");
  assert.equal(isGuessInteractionAllowed("ready_to_guess"), true);
  assert.equal(isGuessInteractionAllowed("judging"), false, "judging must block duplicate guesses and clue reveals");

  const { createAbortDeadline } = loadTypeScriptModule("src/abortDeadline.ts");
  let deadlineCallback;
  let deadlineCleared = 0;
  const fakeClock = {
    set: (callback) => {
      deadlineCallback = callback;
      return 41;
    },
    clear: () => { deadlineCleared += 1; },
  };
  const deadline = createAbortDeadline(undefined, 8_000, fakeClock);
  const neverSettlingPoll = new Promise(() => {});
  void neverSettlingPoll;
  deadlineCallback();
  assert.equal(deadline.didTimeout(), true, "a never-settling poll/API request is aborted by its deadline");
  assert.equal(deadline.signal.aborted, true);
  deadline.dispose();
  assert.equal(deadlineCleared, 1);
  let added = 0;
  let removed = 0;
  const fakeCallerSignal = {
    aborted: false,
    reason: undefined,
    addEventListener: () => { added += 1; },
    removeEventListener: () => { removed += 1; },
  };
  const composed = createAbortDeadline(fakeCallerSignal, 60_000);
  composed.dispose();
  assert.equal(added, 1);
  assert.equal(removed, 1, "disposing a composed deadline removes its caller listener");
  const callerController = new AbortController();
  const callerAbortedDeadline = createAbortDeadline(callerController.signal, 45_000);
  callerController.abort(new Error("backgrounded"));
  assert.equal(callerAbortedDeadline.signal.aborted, true, "the caller can still abort a request with an endpoint deadline");
  assert.equal(callerAbortedDeadline.didTimeout(), false, "caller abort must not be reported as an endpoint timeout");
  callerAbortedDeadline.dispose();

  const requestTimeoutsPath = path.join(root, "src/requestTimeouts.ts");
  assert.equal(fs.existsSync(requestTimeoutsPath), true, "submit-guess must declare its longer endpoint deadline");
  const { JUDGE_PROVIDER_TIMEOUT_MS, SUBMIT_GUESS_TIMEOUT_MS } = loadTypeScriptModule("src/requestTimeouts.ts");
  assert.equal(JUDGE_PROVIDER_TIMEOUT_MS, 35_000);
  assert.equal(SUBMIT_GUESS_TIMEOUT_MS, 45_000);
  assert.ok(SUBMIT_GUESS_TIMEOUT_MS > JUDGE_PROVIDER_TIMEOUT_MS, "the client must not detach before a valid slow judge finishes");

  const { parseAppLink } = loadTypeScriptModule("src/utils/deepLinks.ts");
  assert.deepEqual(parseAppLink("aipictionary://invite/abcDEF_123-xyz"), {
    kind: "invite",
    code: "abcDEF_123-xyz",
  });
  assert.deepEqual(parseAppLink("aipictionary://game/123e4567-e89b-12d3-a456-426614174000"), {
    kind: "game",
    gameId: "123e4567-e89b-12d3-a456-426614174000",
  });
  assert.deepEqual(parseAppLink("https://play.example/game/123e4567-e89b-12d3-a456-426614174000"), {
    kind: "game",
    gameId: "123e4567-e89b-12d3-a456-426614174000",
  });
  assert.equal(parseAppLink("aipictionary://invite/x"), null);
  assert.equal(parseAppLink("aipictionary://game/not-a-uuid"), null);
  assert.equal(parseAppLink("aipictionary://invite/abc123/extra"), null);
  assert.equal(parseAppLink("aipictionary://invite/abc%2Fdef"), null);
  assert.equal(parseAppLink("aipictionary://game/123e4567-e89b-12d3-a456-426614174000/extra"), null);
  assert.equal(parseAppLink("aipictionary://game/%E0%A4%A"), null);
  assert.equal(parseAppLink("ftp://play.example/invite/abcDEF_123-xyz"), null);
  assert.equal(parseAppLink("javascript:alert(1)"), null);

  const { artifactProvider, isMockArtifact } = loadTypeScriptModule("src/utils/providerProvenance.ts");
  assert.equal(artifactProvider([{ provider_used: null }, { provider_used: "openrouter" }]), "openrouter");
  assert.equal(artifactProvider([{ provider_used: "mock" }]), "mock");
  assert.equal(isMockArtifact([{ provider_used: "mock" }]), true);
  assert.equal(isMockArtifact([{ provider_used: null }]), false);

  const { clampPersistedClueCount } = loadTypeScriptModule("src/clueRevealState.ts");
  assert.equal(clampPersistedClueCount(1, 3), 1);
  assert.equal(clampPersistedClueCount(2, 3), 2);
  assert.equal(clampPersistedClueCount(99, 3), 3);
  assert.equal(clampPersistedClueCount(0, 3), 1);

  const { assertReleaseApiUrl } = loadTypeScriptModule("src/apiUrlSafety.ts");
  assert.equal(assertReleaseApiUrl("http://localhost:8000", true), "http://localhost:8000");
  assert.throws(() => assertReleaseApiUrl("http://localhost:8000", false), /non-loopback/);
  assert.throws(() => assertReleaseApiUrl("http://127.0.0.1:8000", false), /non-loopback/);
  assert.throws(() => assertReleaseApiUrl("", false), /non-loopback/);
  assert.equal(assertReleaseApiUrl("https://api.example.test", false), "https://api.example.test");

  const app = read("App.tsx");
  const events = read("src/hooks/useGameEvents.ts");
  const gamesApi = read("src/api/games.ts");
  const roundsApi = read("src/api/rounds.ts");
  const waiting = read("src/screens/WaitingScreen.tsx");
  const guess = read("src/screens/GuessScreen.tsx");
  const result = read("src/screens/ResultScreen.tsx");
  const invite = read("src/screens/InviteScreen.tsx");
  const profile = read("src/screens/ProfileScreen.tsx");
  const createRound = read("src/screens/CreateRoundScreen.tsx");
  const client = read("src/api/client.ts");
  const roundLifecycle = read("src/roundLifecycle.ts");
  const requestTimeouts = read("src/requestTimeouts.ts");
  const gameTypes = read("src/types/game.ts");
  const statusPill = read("src/components/StatusPill.tsx");

  assert.match(app, /createRequestScope/);
  assert.match(app, /AppStateStatus/);
  assert.match(app, /pendingGameId/);
  assert.match(app, /createLatestTargetCoordinator/);
  assert.match(app, /retireGameOpenWork\("preserve-pending"\)/);
  assert.match(app, /retireGameOpenWork\("clear-pending"\)/);
  assert.match(app, /if \(!user \|\| !pendingGameId \|\| !appIsActive\) return;\s+void openGameById\(pendingGameId\)/);
  assert.match(app, /gameOpenRetirementGenerationRef/);
  assert.match(app, /createActionContextGuard/);
  assert.match(app, /retireActionWork/);
  assert.match(app, /selectedRefreshOperation\.retire/);
  assert.match(roundLifecycle, /latestRound\.status === "ready_to_guess" \|\| latestRound\.status === "judging"/);
  assert.match(app, /observedGuessRoundIdRef/);
  assert.match(app, /request\.signal/);
  assert.match(events, /userId/);
  assert.match(events, /connectionGeneration/);
  assert.match(events, /createRealtimeCursor/);
  assert.match(events, /pollTimer/);
  assert.match(events, /AbortController/);
  assert.match(events, /failurePolicy\.healthy/);
  assert.match(events, /POLL_TIMEOUT_MS/);
  assert.match(client, /DEFAULT_API_TIMEOUT_MS/);
  assert.match(client, /createAbortDeadline/);
  assert.match(client, /timeoutMs \?\? DEFAULT_API_TIMEOUT_MS/);
  assert.match(requestTimeouts, /SUBMIT_GUESS_TIMEOUT_MS = JUDGE_PROVIDER_TIMEOUT_MS \+ 10_000/);
  assert.match(gamesApi, /signal\?: AbortSignal/);
  assert.match(roundsApi, /signal\?: AbortSignal/);
  assert.match(roundsApi, /revealClue/);
  assert.match(roundsApi, /timeoutMs: SUBMIT_GUESS_TIMEOUT_MS/);
  assert.doesNotMatch(roundsApi, /clue_count_used/);
  assert.match(guess, /round\.clue_reveal_count/);
  assert.match(guess, /revealClue/);
  assert.match(guess, /revealInFlight/);
  assert.match(guess, /isGuessInteractionAllowed/);
  assert.match(guess, /Scoring your guess/);
  assert.match(guess, /\[lifecycleEpoch, round\.id\]/);
  assert.match(gameTypes, /"judging"/);
  assert.match(statusPill, /status === "judging"/);
  assert.match(waiting, /Scoring guess/);
  for (const source of [waiting, guess, result]) {
    assert.match(source, /Mock output — testing only/);
    assert.doesNotMatch(source, /isDev && isMock/);
  }
  for (const source of [waiting, guess, invite, profile, createRound]) {
    assert.match(source, /useRef/);
    assert.match(source, /lifecycleEpoch/);
    assert.match(source, /Controller\.current === controller/);
  }

  console.log("task5 lifecycle checks passed");
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
