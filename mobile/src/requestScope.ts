export type ScopedRequest = {
  signal: AbortSignal;
  isCurrent: () => boolean;
  runIfCurrent: <T>(apply: () => T) => T | undefined;
  finish: () => void;
};

export type RequestScope = {
  activate: (key: string) => void;
  retire: () => void;
  begin: (key: string) => ScopedRequest;
};

export function createRequestScope(): RequestScope {
  let active = false;
  let currentKey: string | null = null;
  let generation = 0;
  const controllers = new Set<AbortController>();

  function abortAll() {
    for (const controller of controllers) controller.abort();
    controllers.clear();
  }

  return {
    activate(key) {
      if (active && currentKey === key) return;
      abortAll();
      active = true;
      currentKey = key;
      generation += 1;
    },
    retire() {
      abortAll();
      active = false;
      currentKey = null;
      generation += 1;
    },
    begin(key) {
      const controller = new AbortController();
      const capturedGeneration = generation;
      const isCurrent = () =>
        active &&
        currentKey === key &&
        capturedGeneration === generation &&
        !controller.signal.aborted;
      controllers.add(controller);
      return {
        signal: controller.signal,
        isCurrent,
        runIfCurrent: (apply) => (isCurrent() ? apply() : undefined),
        finish: () => controllers.delete(controller),
      };
    },
  };
}
