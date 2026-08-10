const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

const root = path.resolve(__dirname, "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");

const app = read("App.tsx");
const bootstrap = read("src/sessionBootstrap.ts");
const events = read("src/hooks/useGameEvents.ts");
const invites = read("src/api/invites.ts");
const createRound = read("src/screens/CreateRoundScreen.tsx");

assert.match(bootstrap, /return "retry"/);
const compiledBootstrap = ts.transpileModule(bootstrap, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const bootstrapModule = { exports: {} };
new Function("exports", "module", compiledBootstrap)(bootstrapModule.exports, bootstrapModule);
const { decideSessionBootstrap } = bootstrapModule.exports;
assert.equal(decideSessionBootstrap(false, false), "reonboard");
assert.equal(decideSessionBootstrap(true, true), "restore");
assert.equal(decideSessionBootstrap(true, true, "unauthorized"), "reonboard");
assert.equal(decideSessionBootstrap(true, true, "transient"), "retry");
assert.match(app, /isUnauthorizedError/);
assert.match(app, /startup_error/);
assert.doesNotMatch(events, /access_token=/);
assert.match(events, /createWebSocketTicket/);
assert.doesNotMatch(invites, /\/invites\/\$\{/);
assert.match(invites, /\/invites\/preview/);
assert.match(invites, /\/invites\/join/);
assert.doesNotMatch(createRound, /console\.(log|warn|error)/);
assert.doesNotMatch(createRound, /finalPrompt\s*[,}]/);
assert.doesNotMatch(createRound, /returnedPrompt/);
assert.doesNotMatch(createRound, /Submitting prompt:/);

console.log("task3 security source checks passed");
