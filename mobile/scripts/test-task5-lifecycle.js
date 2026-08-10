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
  assert.match(app, /request\.signal/);
  assert.match(events, /userId/);
  assert.match(events, /connectionGeneration/);
  assert.match(events, /pollTimer/);
  assert.match(events, /AbortController/);
  assert.match(events, /failurePolicy\.healthy/);
  assert.match(events, /POLL_TIMEOUT_MS/);
  assert.match(client, /DEFAULT_API_TIMEOUT_MS/);
  assert.match(client, /createAbortDeadline/);
  assert.match(gamesApi, /signal\?: AbortSignal/);
  assert.match(roundsApi, /signal\?: AbortSignal/);
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
