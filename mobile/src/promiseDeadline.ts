import type { WorkSettlement } from "./identityWorkCoordinator";

export function settleWithin<Value>(promise: Promise<Value>, timeoutMs: number): Promise<WorkSettlement<Value>> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      resolve({ status: "timeout" });
    }, timeoutMs);

    promise.then(
      (value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve({ status: "completed", value });
      },
      (error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

export async function runWithDeadline<Value>(
  operation: (signal: AbortSignal) => Promise<Value>,
  timeoutMs: number,
): Promise<WorkSettlement<Value>> {
  const controller = new AbortController();
  const operationPromise = Promise.resolve().then(() => operation(controller.signal));
  const settlement = await settleWithin(operationPromise, timeoutMs);
  if (settlement.status === "timeout") controller.abort();
  return settlement;
}
