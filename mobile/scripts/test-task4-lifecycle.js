const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

const root = path.resolve(__dirname, "..");

function loadTypeScriptModule(relativePath) {
  const source = fs.readFileSync(path.join(root, relativePath), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const loaded = { exports: {} };
  new Function("exports", "module", compiled)(loaded.exports, loaded);
  return loaded.exports;
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function run() {
  const { createSessionEpoch } = loadTypeScriptModule("src/sessionEpoch.ts");
  const epoch = createSessionEpoch();
  const oldEpoch = epoch.capture();
  const delayed = deferred();
  const applied = [];
  const completion = delayed.promise.then(() => epoch.runIfCurrent(oldEpoch, () => applied.push("old")));
  epoch.retire();
  delayed.resolve();
  await completion;
  assert.deepEqual(applied, [], "a delayed pre-reset completion must not restore state");
  const activeEpoch = epoch.activate();
  epoch.runIfCurrent(activeEpoch, () => applied.push("new"));
  assert.deepEqual(applied, ["new"]);

  const { createIdentityWorkCoordinator } = loadTypeScriptModule("src/identityWorkCoordinator.ts");
  const registrations = [];
  const cleanups = [];
  const accepted = [];
  const work = { A: deferred(), B: deferred() };
  let credentialIdentity = "A";
  const coordinator = createIdentityWorkCoordinator({
    run: async (identity) => {
      registrations.push(identity);
      return work[identity].promise;
    },
    cleanup: async (identity, result) => cleanups.push(`${identity}:${result.token}`),
    canCleanup: (identity) => identity === credentialIdentity,
    accept: (identity) => accepted.push(identity),
    reject: () => {},
  });

  const registrationA = coordinator.activate("A");
  await Promise.resolve();
  credentialIdentity = "B";
  const registrationB = coordinator.activate("B");
  assert.deepEqual(registrations, ["A"], "B waits for older identity work instead of reusing it");
  work.A.resolve({ token: "token-a" });
  await registrationA;
  await Promise.resolve();
  assert.deepEqual(registrations, ["A", "B"], "latest identity gets a fresh registration");
  work.B.resolve({ token: "token-b" });
  await registrationB;
  assert.deepEqual(accepted, ["B"]);
  credentialIdentity = "A";
  await coordinator.retire("A");
  assert.ok(cleanups.includes("A:token-a"), "stale A work is retained until A credentials can clean it");

  const retiringWork = deferred();
  credentialIdentity = "C";
  const retiring = createIdentityWorkCoordinator({
    run: async () => retiringWork.promise,
    cleanup: async (identity, result) => cleanups.push(`${identity}:${result.token}`),
    canCleanup: (identity) => identity === credentialIdentity,
    accept: () => {},
    reject: () => {},
  });
  const pendingC = retiring.activate("C");
  await Promise.resolve();
  const retiredC = retiring.retire("C");
  retiringWork.resolve({ token: "token-c" });
  await Promise.all([pendingC, retiredC]);
  assert.ok(cleanups.includes("C:token-c"), "retirement cleans pending work while C credentials remain active");

  const app = fs.readFileSync(path.join(root, "App.tsx"), "utf8");
  const events = fs.readFileSync(path.join(root, "src/hooks/useGameEvents.ts"), "utf8");
  assert.match(app, /sessionEpoch\.retire\(\)/);
  assert.match(app, /runIfCurrent/);
  assert.match(events, /if \(closed\) return/);
  console.log("task4 lifecycle checks passed");
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
