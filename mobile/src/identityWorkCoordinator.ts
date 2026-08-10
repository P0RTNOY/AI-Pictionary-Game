type IdentityWorkCallbacks<Result> = {
  run: (identity: string) => Promise<Result>;
  cleanup: (identity: string, result: Result) => Promise<void>;
  canCleanup: (identity: string) => boolean;
  accept: (identity: string, result: Result) => void;
  reject: (identity: string, error: unknown) => void;
};

export type IdentityWorkCoordinator<Result> = {
  activate: (identity: string) => Promise<Result | null>;
  retire: (identity: string) => Promise<void>;
};

export function createIdentityWorkCoordinator<Result>(
  callbacks: IdentityWorkCallbacks<Result>,
): IdentityWorkCoordinator<Result> {
  let generation = 0;
  let currentIdentity: string | null = null;
  const accepted = new Map<string, Result>();
  const active = new Map<string, Promise<Result | null>>();

  function activate(identity: string): Promise<Result | null> {
    const existing = active.get(identity);
    if (existing && currentIdentity === identity) return existing;

    currentIdentity = identity;
    const workGeneration = ++generation;
    const blockers = [...active.entries()]
      .filter(([activeIdentity]) => activeIdentity !== identity)
      .map(([, work]) => work);
    const work = (async () => {
      await Promise.allSettled(blockers);
      if (currentIdentity !== identity || generation !== workGeneration) return null;
      try {
        const result = await callbacks.run(identity);
        if (currentIdentity !== identity || generation !== workGeneration) {
          if (callbacks.canCleanup(identity)) await callbacks.cleanup(identity, result);
          else accepted.set(identity, result);
          return null;
        }
        accepted.set(identity, result);
        callbacks.accept(identity, result);
        return result;
      } catch (error) {
        if (currentIdentity === identity && generation === workGeneration) {
          callbacks.reject(identity, error);
        }
        return null;
      }
    })();
    active.set(identity, work);
    void work.finally(() => {
      if (active.get(identity) === work) active.delete(identity);
    });
    return work;
  }

  async function retire(identity: string): Promise<void> {
    if (currentIdentity === identity) {
      currentIdentity = null;
      generation += 1;
    }
    const pending = active.get(identity);
    if (pending) await pending;
    if (accepted.has(identity) && callbacks.canCleanup(identity)) {
      const retiring = accepted.get(identity)!;
      accepted.delete(identity);
      await callbacks.cleanup(identity, retiring);
    }
  }

  return { activate, retire };
}
