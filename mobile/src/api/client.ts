import { API_URL } from "../config";
import { captureError } from "../utils/errorReporter";
import { createAbortDeadline } from "../abortDeadline";

export { API_URL };

let apiAccessToken: string | null = null;

const configuredTimeout = Number(process.env.EXPO_PUBLIC_API_TIMEOUT_MS);
export const DEFAULT_API_TIMEOUT_MS =
  Number.isFinite(configuredTimeout) && configuredTimeout >= 1_000 && configuredTimeout <= 60_000
    ? configuredTimeout
    : 15_000;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class ApiTimeoutError extends Error {
  constructor() {
    super("The request timed out. Check the connection and try again.");
    this.name = "ApiTimeoutError";
  }
}

export function configureApiCredential(accessToken: string | null) {
  apiAccessToken = accessToken;
}

export function getApiCredential() {
  return apiAccessToken;
}

export function isUnauthorizedError(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status === 401;
}

export type ApiFetchOptions = RequestInit & { timeoutMs?: number };

function telemetryUrl(path: string) {
  return path.startsWith("/invites/") ? `${API_URL}/invites/{code}` : `${API_URL}${path}`;
}

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
  accessTokenOverride?: string | null,
): Promise<T> {
  const url = `${API_URL}${path}`;
  const { timeoutMs, ...requestOptions } = options;
  const deadline = createAbortDeadline(requestOptions.signal ?? undefined, timeoutMs ?? DEFAULT_API_TIMEOUT_MS);
  try {
    const headers = new Headers(requestOptions.headers);
    headers.set("Content-Type", "application/json");
    const accessToken = accessTokenOverride === undefined ? apiAccessToken : accessTokenOverride;
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    else headers.delete("Authorization");
    const response = await fetch(url, {
      ...requestOptions,
      headers,
      signal: deadline.signal,
    });
    if (!response.ok) {
      throw new ApiError(response.status, await response.text());
    }
    return response.json();
  } catch (error) {
    captureError(error, { area: "api", url: telemetryUrl(path), method: requestOptions.method ?? "GET" });
    if (deadline.didTimeout()) throw new ApiTimeoutError();
    if (error instanceof TypeError) {
      throw new Error(`Could not reach backend at ${API_URL}. Check the API URL and network.`);
    }
    throw error;
  } finally {
    deadline.dispose();
  }
}

export async function healthCheck(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/health");
}
