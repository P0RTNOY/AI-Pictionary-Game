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

async function waitFor(predicate, message) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (predicate()) return;
    await Promise.resolve();
  }
  assert.fail(message);
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
  const sessionA = { key: "session-a", identity: "A", credential: "credential-a" };
  const sessionB = { key: "session-b", identity: "B", credential: "credential-b" };
  const work = { "session-a": deferred(), "session-b": deferred() };
  const coordinator = createIdentityWorkCoordinator({
    sessionKey: (session) => session.key,
    run: async (session) => {
      registrations.push(`${session.identity}:${session.credential}`);
      return work[session.key].promise;
    },
    cleanup: async (session, result) => cleanups.push(`${session.identity}:${session.credential}:${result.token}`),
    accept: (session) => accepted.push(session.identity),
    reject: () => {},
    settle: async (promise) => ({ status: "completed", value: await promise }),
  });

  const registrationA = coordinator.activate(sessionA);
  await Promise.resolve();
  const registrationB = coordinator.activate(sessionB);
  assert.deepEqual(registrations, ["A:credential-a"], "B waits for older identity work instead of reusing it");
  work["session-a"].resolve({ token: "token-a" });
  await registrationA;
  await waitFor(() => registrations.length === 2, "B should begin after stale A cleanup settles");
  assert.deepEqual(cleanups, ["A:credential-a:token-a"], "stale A cleanup stays bound to A's bearer");
  assert.deepEqual(registrations, ["A:credential-a", "B:credential-b"], "latest identity gets a fresh registration");
  work["session-b"].resolve({ token: "token-b" });
  await registrationB;
  assert.deepEqual(accepted, ["B"]);

  const sessionA2 = { key: "session-a-rotated", identity: "A", credential: "credential-a-rotated" };
  const rotatedWork = deferred();
  work[sessionA2.key] = rotatedWork;
  const registrationA2 = coordinator.activate(sessionA2);
  await Promise.resolve();
  rotatedWork.resolve({ token: "token-a-rotated" });
  await registrationA2;
  assert.deepEqual(accepted, ["B", "A"], "returning A accepts only its rotated session result");
  assert.deepEqual(cleanups, ["A:credential-a:token-a"], "old A cannot overwrite or clean with the rotated bearer");

  const retiringWork = deferred();
  const sessionC = { key: "session-c", identity: "C", credential: "credential-c" };
  const retiring = createIdentityWorkCoordinator({
    sessionKey: (session) => session.key,
    run: async () => retiringWork.promise,
    cleanup: async (session, result) => cleanups.push(`${session.identity}:${session.credential}:${result.token}`),
    accept: () => {},
    reject: () => {},
    settle: async (promise) => ({ status: "completed", value: await promise }),
  });
  const pendingC = retiring.activate(sessionC);
  await Promise.resolve();
  const retiredC = retiring.retire(sessionC);
  retiringWork.resolve({ token: "token-c" });
  await Promise.all([pendingC, retiredC]);
  assert.ok(cleanups.includes("C:credential-c:token-c"), "retirement cleans pending work with C's captured bearer");

  const never = new Promise(() => {});
  const neverRegistrations = [];
  const bounded = createIdentityWorkCoordinator({
    sessionKey: (session) => session.key,
    run: async (session) => {
      neverRegistrations.push(session.identity);
      return session.identity === "A" ? never : { token: "token-b" };
    },
    cleanup: async () => {},
    accept: () => {},
    reject: () => {},
    settle: async (promise, label) =>
      label.includes("session-a") ? { status: "timeout" } : { status: "completed", value: await promise },
  });
  const neverA = bounded.activate(sessionA);
  await Promise.resolve();
  const boundedB = bounded.activate(sessionB);
  await Promise.all([neverA, boundedB]);
  assert.deepEqual(neverRegistrations, ["A", "B"], "B begins after A's deadline even when A never settles");
  await bounded.retire(sessionA);

  const sessionD = { key: "session-d", identity: "D", credential: "credential-d" };
  const boundedCleanup = createIdentityWorkCoordinator({
    sessionKey: (session) => session.key,
    run: async () => ({ token: "token-d" }),
    cleanup: async () => never,
    accept: () => {},
    reject: () => {},
    settle: async (promise, label) =>
      label === "cleanup:session-d" ? { status: "timeout" } : { status: "completed", value: await promise },
  });
  await boundedCleanup.activate(sessionD);
  await boundedCleanup.retire(sessionD);

  const cleanupGate = deferred();
  const sequencing = [];
  const sequenced = createIdentityWorkCoordinator({
    sessionKey: (session) => session.key,
    run: async (session) => {
      sequencing.push(`register:${session.credential}`);
      return { token: "shared-token" };
    },
    cleanup: async (session) => {
      sequencing.push(`cleanup-start:${session.credential}`);
      await cleanupGate.promise;
      sequencing.push(`cleanup-end:${session.credential}`);
    },
    accept: () => {},
    reject: () => {},
    settle: async (promise) => ({ status: "completed", value: await promise }),
  });
  await sequenced.activate(sessionA);
  const retiringA = sequenced.retire(sessionA);
  await Promise.resolve();
  const rotatedA = sequenced.activate(sessionA2);
  await Promise.resolve();
  assert.deepEqual(
    sequencing,
    ["register:credential-a", "cleanup-start:credential-a"],
    "rotated registration waits for accepted-session cleanup",
  );
  cleanupGate.resolve();
  await Promise.all([retiringA, rotatedA]);
  assert.deepEqual(sequencing, [
    "register:credential-a",
    "cleanup-start:credential-a",
    "cleanup-end:credential-a",
    "register:credential-a-rotated",
  ]);

  const replacementOrder = [];
  let replacementAttempt = 0;
  const replacing = createIdentityWorkCoordinator({
    sessionKey: (session) => session.key,
    run: async () => {
      replacementAttempt += 1;
      replacementOrder.push(`register:${replacementAttempt}`);
      return { token: `token-${replacementAttempt}` };
    },
    cleanup: async (_session, result) => replacementOrder.push(`cleanup:${result.token}`),
    accept: () => {},
    reject: () => {},
    settle: async (promise) => ({ status: "completed", value: await promise }),
  });
  await replacing.activate(sessionB);
  await replacing.activate(sessionB);
  assert.deepEqual(
    replacementOrder,
    ["register:1", "cleanup:token-1", "register:2"],
    "same-session refresh retires its accepted token before replacing it",
  );

  const overlapWork = [deferred(), deferred()];
  const overlapOrder = [];
  let overlapAttempt = 0;
  const overlapping = createIdentityWorkCoordinator({
    sessionKey: (session) => session.key,
    run: async () => {
      const attempt = overlapAttempt;
      overlapAttempt += 1;
      overlapOrder.push(`register:${attempt + 1}`);
      return overlapWork[attempt].promise;
    },
    cleanup: async (_session, result) => overlapOrder.push(`cleanup:${result.registrationId}`),
    accept: () => {},
    reject: () => {},
    settle: async (promise) => ({ status: "completed", value: await promise }),
  });
  const overlapFirst = overlapping.activate(sessionB);
  await Promise.resolve();
  const overlapSecond = overlapping.activate(sessionB);
  overlapWork[0].resolve({ token: "token-1", registrationId: "registration-1" });
  await overlapFirst;
  await waitFor(() => overlapAttempt === 2, "overlapping refresh should start a fresh attempt");
  assert.deepEqual(overlapOrder, ["register:1", "cleanup:registration-1", "register:2"]);
  overlapWork[1].resolve({ token: "token-2", registrationId: "registration-2" });
  await overlapSecond;

  const { runWithDeadline } = loadTypeScriptModule("src/promiseDeadline.ts");
  let abortedSignal;
  const aborted = await runWithDeadline((signal) => {
    abortedSignal = signal;
    return never;
  }, 0);
  assert.equal(aborted.status, "timeout");
  assert.equal(abortedSignal.aborted, true, "timed-out network work is cancelled");

  const client = fs.readFileSync(path.join(root, "src/api/client.ts"), "utf8");
  const deviceTokens = fs.readFileSync(path.join(root, "src/api/deviceTokens.ts"), "utf8");

  const app = fs.readFileSync(path.join(root, "App.tsx"), "utf8");
  const events = fs.readFileSync(path.join(root, "src/hooks/useGameEvents.ts"), "utf8");
  assert.match(app, /sessionEpoch\.retire\(\)/);
  assert.match(app, /runIfCurrent/);
  assert.match(app, /sessionAccessToken/);
  assert.match(client, /accessTokenOverride/);
  assert.match(deviceTokens, /accessToken/);
  assert.match(deviceTokens, /registration_id/);
  assert.match(events, /if \(closed\) return/);
  console.log("task4 lifecycle checks passed");
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
