const LOCAL_API_URL = "http://localhost:8000";
const RELEASE_ENVIRONMENTS = new Set(["staging", "production"]);

function isLoopbackUrl(value) {
  try {
    const url = new URL(value);
    const hostname = url.hostname.toLowerCase().replace(/^\[|\]$/g, "");
    return (
      !["http:", "https:"].includes(url.protocol) ||
      hostname === "localhost" ||
      hostname === "::1" ||
      hostname === "0.0.0.0" ||
      hostname.endsWith(".localhost") ||
      /^127(?:\.\d{1,3}){3}$/.test(hostname)
    );
  } catch {
    return true;
  }
}

module.exports = ({ config }) => {
  const appEnv = process.env.EXPO_PUBLIC_APP_ENV ?? config.extra?.appEnv ?? "local";
  const apiUrl = process.env.EXPO_PUBLIC_API_URL;

  if (RELEASE_ENVIRONMENTS.has(appEnv) && (!apiUrl || isLoopbackUrl(apiUrl))) {
    throw new Error(
      "EXPO_PUBLIC_API_URL must be a non-loopback URL for staging and production builds. Configure it as a plaintext EAS environment variable."
    );
  }

  return {
    ...config,
    extra: {
      ...config.extra,
      appEnv,
      buildProfile: process.env.EXPO_PUBLIC_BUILD_PROFILE ?? config.extra?.buildProfile ?? "local",
      apiUrl: apiUrl ?? LOCAL_API_URL,
    },
  };
};
