import { API_URL } from "../config";
import { captureError } from "../utils/errorReporter";

export { API_URL };

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_URL}${path}`;
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers ?? {}),
      },
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json();
  } catch (error) {
    captureError(error, { area: "api", url, method: options.method ?? "GET" });
    if (error instanceof TypeError) {
      throw new Error(`Could not reach backend at ${API_URL}. Check the API URL and network.`);
    }
    throw error;
  }
}

export async function healthCheck(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/health");
}
