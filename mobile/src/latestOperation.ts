export type LatestOperationToken = {
  signal: AbortSignal;
  isCurrent: () => boolean;
  settle: () => void;
};

export type LatestOperation = {
  begin: (key: string) => LatestOperationToken;
  retire: () => void;
};

export function createLatestOperation(onLoadingChange: (loading: boolean) => void): LatestOperation {
  let generation = 0;
  let active: { key: string; generation: number; controller: AbortController } | null = null;

  function retire() {
    generation += 1;
    active?.controller.abort();
    if (active) onLoadingChange(false);
    active = null;
  }

  function begin(key: string): LatestOperationToken {
    retire();
    const controller = new AbortController();
    const operationGeneration = ++generation;
    active = { key, generation: operationGeneration, controller };
    onLoadingChange(true);
    const isCurrent = () =>
      active?.key === key &&
      active.generation === operationGeneration &&
      generation === operationGeneration &&
      !controller.signal.aborted;
    return {
      signal: controller.signal,
      isCurrent,
      settle: () => {
        if (!isCurrent()) return;
        active = null;
        onLoadingChange(false);
      },
    };
  }

  return { begin, retire };
}
