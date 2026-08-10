const assert = require("node:assert/strict");

const configFactory = require("../app.config.js");
const baseConfig = require("../app.json").expo;

function getReleaseConfig(apiUrl) {
  const previousAppEnv = process.env.EXPO_PUBLIC_APP_ENV;
  const previousApiUrl = process.env.EXPO_PUBLIC_API_URL;
  process.env.EXPO_PUBLIC_APP_ENV = "production";

  if (apiUrl === undefined) {
    delete process.env.EXPO_PUBLIC_API_URL;
  } else {
    process.env.EXPO_PUBLIC_API_URL = apiUrl;
  }

  try {
    return configFactory({ config: baseConfig });
  } finally {
    if (previousAppEnv === undefined) delete process.env.EXPO_PUBLIC_APP_ENV;
    else process.env.EXPO_PUBLIC_APP_ENV = previousAppEnv;
    if (previousApiUrl === undefined) delete process.env.EXPO_PUBLIC_API_URL;
    else process.env.EXPO_PUBLIC_API_URL = previousApiUrl;
  }
}

const rejectedApiUrls = [
  undefined,
  "http://localhost:8000",
  "http://127.0.0.1:8000",
  "http://127.42.0.1:8000",
  "http://0.0.0.0:8000",
  "http://[::]:8000",
  "http://[::1]:8000",
  "http://[::ffff:127.0.0.1]:8000",
  "http://[::ffff:7f00:1]:8000",
  "http://[::ffff:0:0]:8000",
  "not a URL",
  "ftp://api.example.invalid",
];

for (const apiUrl of rejectedApiUrls) {
  assert.throws(
    () => getReleaseConfig(apiUrl),
    /EXPO_PUBLIC_API_URL must be a non-loopback URL/,
    `expected ${apiUrl ?? "a missing API URL"} to be rejected`
  );
}

const config = getReleaseConfig("https://api.example.invalid");
assert.equal(config.extra.apiUrl, "https://api.example.invalid");

console.log("app-config release API URL guard passed");
