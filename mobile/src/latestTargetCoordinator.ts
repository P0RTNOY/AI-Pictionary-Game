type LatestTargetOptions<Target, Result> = {
  key: (target: Target) => string;
  run: (target: Target, signal: AbortSignal) => Promise<Result>;
  accept: (target: Target, result: Result) => void;
  reject: (target: Target, error: unknown) => void;
  now?: () => number;
  dedupeWindowMs?: number;
  maxRecentTargets?: number;
};

export type LatestTargetCoordinator<Target, Result> = {
  request: (target: Target) => Promise<Result | null>;
  retire: () => void;
};

export function createLatestTargetCoordinator<Target, Result>({
  key,
  run,
  accept,
  reject,
  now = Date.now,
  dedupeWindowMs = 2_000,
  maxRecentTargets = 16,
}: LatestTargetOptions<Target, Result>): LatestTargetCoordinator<Target, Result> {
  let generation = 0;
  let active: { key: string; controller: AbortController; work: Promise<Result | null> } | null = null;
  const recent = new Map<string, number>();

  function pruneRecent(timestamp: number) {
    for (const [recentKey, acceptedAt] of recent) {
      if (timestamp - acceptedAt > dedupeWindowMs) recent.delete(recentKey);
    }
    while (recent.size > maxRecentTargets) {
      const oldest = recent.keys().next().value;
      if (oldest === undefined) break;
      recent.delete(oldest);
    }
  }

  function request(target: Target): Promise<Result | null> {
    const targetKey = key(target);
    const timestamp = now();
    pruneRecent(timestamp);
    if (active?.key === targetKey) return active.work;
    if (recent.has(targetKey)) return Promise.resolve(null);

    active?.controller.abort();
    const controller = new AbortController();
    const requestGeneration = ++generation;
    let work!: Promise<Result | null>;
    work = (async () => {
      try {
        await Promise.resolve();
        const result = await run(target, controller.signal);
        if (controller.signal.aborted || generation !== requestGeneration) return null;
        const acceptedAt = now();
        recent.delete(targetKey);
        recent.set(targetKey, acceptedAt);
        pruneRecent(acceptedAt);
        accept(target, result);
        return result;
      } catch (error) {
        if (!controller.signal.aborted && generation === requestGeneration) reject(target, error);
        return null;
      } finally {
        if (active?.work === work) active = null;
      }
    })();
    active = { key: targetKey, controller, work };
    return work;
  }

  function retire() {
    generation += 1;
    active?.controller.abort();
    active = null;
  }

  return { request, retire };
}
