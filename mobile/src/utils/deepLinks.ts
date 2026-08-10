export const INVITE_SCHEME = "aipictionary";
export const DEV_INVITE_PREFIX = "aipictionary://invite";
export const PROD_INVITE_PREFIX = "https://your-domain.com/invite";

export type AppLink = { kind: "invite"; code: string } | { kind: "game"; gameId: string };

const INVITE_CODE_PATTERN = /^[A-Za-z0-9_-]{6,64}$/;
const GAME_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function buildInviteLink(code: string, mode: "dev" | "prod" = "dev") {
  const normalized = normalizeInviteCode(code);
  return `${mode === "prod" ? PROD_INVITE_PREFIX : DEV_INVITE_PREFIX}/${normalized}`;
}

export function normalizeInviteCode(code: string) {
  return code.trim();
}

export function parseInviteCodeFromUrl(url: string | null | undefined): string | null {
  const link = parseAppLink(url);
  return link?.kind === "invite" ? link.code : null;
}

export function parseAppLink(url: string | null | undefined): AppLink | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== `${INVITE_SCHEME}:` && parsed.protocol !== "https:") return null;
    const pathParts = parsed.pathname.split("/").filter(Boolean);
    const kind = parsed.protocol === `${INVITE_SCHEME}:` ? parsed.hostname : pathParts.shift();
    const value = pathParts.length === 1 ? decodeURIComponent(pathParts[0]) : "";
    if (kind === "invite" && INVITE_CODE_PATTERN.test(value)) return { kind: "invite", code: value };
    if (kind === "game" && GAME_ID_PATTERN.test(value)) return { kind: "game", gameId: value.toLowerCase() };
  } catch {
    return null;
  }
  return null;
}
