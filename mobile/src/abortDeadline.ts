export type AbortDeadline = {
  signal: AbortSignal;
  didTimeout: () => boolean;
  dispose: () => void;
};

type DeadlineClock = {
  set: (callback: () => void, timeoutMs: number) => ReturnType<typeof setTimeout>;
  clear: (timer: ReturnType<typeof setTimeout>) => void;
};

export function createAbortDeadline(
  callerSignal: AbortSignal | undefined,
  timeoutMs: number,
  clock: DeadlineClock = { set: setTimeout, clear: clearTimeout },
): AbortDeadline {
  const controller = new AbortController();
  let timedOut = false;
  let disposed = false;

  const onCallerAbort = () => controller.abort(callerSignal?.reason);
  if (callerSignal?.aborted) onCallerAbort();
  else callerSignal?.addEventListener("abort", onCallerAbort, { once: true });

  const timer = clock.set(() => {
    timedOut = true;
    controller.abort(new Error("Request deadline exceeded"));
  }, Math.max(0, timeoutMs));

  return {
    signal: controller.signal,
    didTimeout: () => timedOut,
    dispose: () => {
      if (disposed) return;
      disposed = true;
      clock.clear(timer);
      callerSignal?.removeEventListener("abort", onCallerAbort);
    },
  };
}
