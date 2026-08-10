const { isIP } = require("node:net");

const LOCAL_API_URL = "http://localhost:8000";
const RELEASE_ENVIRONMENTS = new Set(["staging", "production"]);
const RELEASE_BUILD_PROFILES = new Set(["preview", "production"]);

function isIpv4LoopbackOrUnspecified(hostname) {
  if (isIP(hostname) !== 4) return false;
  const octets = hostname.split(".").map(Number);
  return octets[0] === 127 || octets.every((octet) => octet === 0);
}

function mappedIpv4Octets(hostname) {
  const match = hostname.match(/^::ffff:([0-9a-f]{1,4}):([0-9a-f]{1,4})$/);
  if (!match) return null;

  const highWord = Number.parseInt(match[1], 16);
  const lowWord = Number.parseInt(match[2], 16);
  return [highWord >> 8, highWord & 0xff, lowWord >> 8, lowWord & 0xff];
}

function isLoopbackUrl(value) {
  try {
    const url = new URL(value);
    const hostname = url.hostname.toLowerCase().replace(/^\[|\]$/g, "");
    const mappedIpv4 = mappedIpv4Octets(hostname);
    return (
      !["http:", "https:"].includes(url.protocol) ||
      hostname === "localhost" ||
      hostname === "localhost." ||
      hostname === "::1" ||
      hostname === "::" ||
      hostname === "0.0.0.0" ||
      hostname.endsWith(".localhost") ||
      hostname.endsWith(".localhost.") ||
      isIpv4LoopbackOrUnspecified(hostname) ||
      (mappedIpv4 !== null && (mappedIpv4[0] === 127 || mappedIpv4.every((octet) => octet === 0)))
    );
  } catch {
    return true;
  }
}

module.exports = ({ config }) => {
  const appEnv = process.env.EXPO_PUBLIC_APP_ENV ?? config.extra?.appEnv ?? "local";
  const buildProfile = process.env.EXPO_PUBLIC_BUILD_PROFILE ?? process.env.EAS_BUILD_PROFILE ?? config.extra?.buildProfile ?? "local";
  const apiUrl = process.env.EXPO_PUBLIC_API_URL;

  if ((RELEASE_ENVIRONMENTS.has(appEnv) || RELEASE_BUILD_PROFILES.has(buildProfile)) && (!apiUrl || isLoopbackUrl(apiUrl))) {
    throw new Error(
      "EXPO_PUBLIC_API_URL must be a non-loopback URL for staging and production builds. Configure it as a plaintext EAS environment variable."
    );
  }

  return {
    ...config,
    extra: {
      ...config.extra,
      appEnv,
      buildProfile,
      apiUrl: apiUrl ?? LOCAL_API_URL,
    },
  };
};
