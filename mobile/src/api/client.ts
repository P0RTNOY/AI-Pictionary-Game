import { API_URL } from "../config";
import { captureError } from "../utils/errorReporter";

export { API_URL };

let apiAccessToken: string | null = null;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
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

function telemetryUrl(path: string) {
  return path.startsWith("/invites/") ? `${API_URL}/invites/{code}` : `${API_URL}${path}`;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  accessTokenOverride?: string | null,
): Promise<T> {
  const url = `${API_URL}${path}`;
  try {
    const headers = new Headers(options.headers);
    headers.set("Content-Type", "application/json");
    const accessToken = accessTokenOverride === undefined ? apiAccessToken : accessTokenOverride;
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    else headers.delete("Authorization");
    const response = await fetch(url, {
      ...options,
      headers,
    });
    if (!response.ok) {
      throw new ApiError(response.status, await response.text());
    }
    return response.json();
  } catch (error) {
    captureError(error, { area: "api", url: telemetryUrl(path), method: options.method ?? "GET" });
    if (error instanceof TypeError) {
      throw new Error(`Could not reach backend at ${API_URL}. Check the API URL and network.`);
    }
    throw error;
  }
}

export async function healthCheck(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/health");
}
