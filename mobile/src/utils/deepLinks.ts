export const INVITE_SCHEME = "aipictionary";
export const DEV_INVITE_PREFIX = "aipictionary://invite";
export const PROD_INVITE_PREFIX = "https://your-domain.com/invite";

export function buildInviteLink(code: string, mode: "dev" | "prod" = "dev") {
  const normalized = normalizeInviteCode(code);
  return `${mode === "prod" ? PROD_INVITE_PREFIX : DEV_INVITE_PREFIX}/${normalized}`;
}

export function normalizeInviteCode(code: string) {
  return code.trim().replace(/[^a-zA-Z0-9]/g, "").toUpperCase();
}

export function parseInviteCodeFromUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol === `${INVITE_SCHEME}:`) {
      if (parsed.hostname === "invite") return normalizeInviteCode(parsed.pathname.replace("/", ""));
      if (parsed.pathname.startsWith("/invite/")) return normalizeInviteCode(parsed.pathname.replace("/invite/", ""));
    }
    if (parsed.protocol === "https:" && parsed.pathname.startsWith("/invite/")) {
      return normalizeInviteCode(parsed.pathname.replace("/invite/", ""));
    }
  } catch {
    const match = url.match(/(?:invite\/)([a-zA-Z0-9]+)/);
    return match ? normalizeInviteCode(match[1]) : null;
  }
  return null;
}
