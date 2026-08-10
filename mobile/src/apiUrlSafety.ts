function isUnsafeApiUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    const hostname = parsed.hostname.toLowerCase().replace(/^\[|\]$/g, "");
    const ipv4 = hostname.split(".").map(Number);
    const isIpv4 = ipv4.length === 4 && ipv4.every((part) => Number.isInteger(part) && part >= 0 && part <= 255);
    return (
      !["http:", "https:"].includes(parsed.protocol) ||
      hostname === "localhost" ||
      hostname === "localhost." ||
      hostname.endsWith(".localhost") ||
      hostname.endsWith(".localhost.") ||
      hostname === "::" ||
      hostname === "::1" ||
      (isIpv4 && (ipv4[0] === 127 || ipv4.every((part) => part === 0))) ||
      /^::ffff:(127\.|7f[0-9a-f]{2}:|0\.0\.0\.0$|0:0$)/i.test(hostname)
    );
  } catch {
    return true;
  }
}

export function assertReleaseApiUrl(value: string, isDevelopment: boolean): string {
  if (!isDevelopment && isUnsafeApiUrl(value)) {
    throw new Error("A native release requires a valid non-loopback EXPO_PUBLIC_API_URL.");
  }
  return value;
}
