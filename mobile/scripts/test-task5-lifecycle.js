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

  assert.match(app, /createRequestScope/);
  assert.match(app, /AppStateStatus/);
  assert.match(app, /pendingGameId/);
  assert.match(app, /request\.signal/);
  assert.match(events, /userId/);
  assert.match(events, /connectionGeneration/);
  assert.match(events, /pollTimer/);
  assert.match(events, /AbortController/);
  assert.match(gamesApi, /signal\?: AbortSignal/);
  assert.match(roundsApi, /signal\?: AbortSignal/);
  for (const source of [waiting, guess, result]) {
    assert.match(source, /Mock output — testing only/);
    assert.doesNotMatch(source, /isDev && isMock/);
  }
  for (const source of [waiting, guess, invite, profile, createRound]) {
    assert.match(source, /useRef/);
  }

  console.log("task5 lifecycle checks passed");
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
