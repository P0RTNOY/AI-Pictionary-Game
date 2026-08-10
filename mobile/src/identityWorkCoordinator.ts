export type WorkSettlement<Value> =
  | { status: "completed"; value: Value }
  | { status: "timeout" };

type IdentityWorkCallbacks<Session, Result> = {
  sessionKey: (session: Session) => string;
  run: (session: Session) => Promise<Result>;
  cleanup: (session: Session, result: Result) => Promise<void>;
  accept: (session: Session, result: Result) => void;
  reject: (session: Session, error: unknown) => void;
  settle: <Value>(promise: Promise<Value>, label: string) => Promise<WorkSettlement<Value>>;
};

export type IdentityWorkCoordinator<Session, Result> = {
  activate: (session: Session) => Promise<Result | null>;
  retire: (session: Session) => Promise<void>;
};

export function createIdentityWorkCoordinator<Session, Result>(
  callbacks: IdentityWorkCallbacks<Session, Result>,
): IdentityWorkCoordinator<Session, Result> {
  let generation = 0;
  let currentKey: string | null = null;
  const accepted = new Map<string, { session: Session; result: Result }>();
  const active = new Map<string, { session: Session; work: Promise<Result | null> }>();

  async function cleanup(session: Session, result: Result, key: string): Promise<void> {
    try {
      await callbacks.settle(callbacks.cleanup(session, result), `cleanup:${key}`);
    } catch {
      // Cleanup is best-effort and must never pin a newer session behind an older one.
    }
  }

  function activate(session: Session): Promise<Result | null> {
    const key = callbacks.sessionKey(session);
    const existing = active.get(key);
    if (existing && currentKey === key) return existing.work;

    currentKey = key;
    const workGeneration = ++generation;
    const blockers = [...active.entries()]
      .filter(([activeKey]) => activeKey !== key)
      .map(([, entry]) => entry.work);
    const work = (async () => {
      try {
        if (blockers.length > 0) {
          // A timed-out predecessor is detached so the latest session may continue.
          await callbacks.settle(Promise.allSettled(blockers), `blockers:${key}`);
        }
        if (currentKey !== key || generation !== workGeneration) return null;

        const runSettlement = await callbacks.settle(callbacks.run(session), `run:${key}`);
        if (runSettlement.status === "timeout") {
          if (currentKey === key && generation === workGeneration) {
            callbacks.reject(session, new Error("Identity work timed out"));
          }
          return null;
        }

        const result = runSettlement.value;
        if (currentKey !== key || generation !== workGeneration) {
          await cleanup(session, result, key);
          return null;
        }
        accepted.set(key, { session, result });
        callbacks.accept(session, result);
        return result;
      } catch (error) {
        if (currentKey === key && generation === workGeneration) callbacks.reject(session, error);
        return null;
      }
    })();
    active.set(key, { session, work });
    void work.finally(() => {
      if (active.get(key)?.work === work) active.delete(key);
    });
    return work;
  }

  async function retire(session: Session): Promise<void> {
    const key = callbacks.sessionKey(session);
    if (currentKey === key) {
      currentKey = null;
      generation += 1;
    }
    const pending = active.get(key);
    if (pending) {
      try {
        await callbacks.settle(pending.work, `retire:${key}`);
      } catch {
        // Retirement remains bounded even if the underlying operation rejects.
      }
    }
    const retiring = accepted.get(key);
    if (retiring) {
      accepted.delete(key);
      await cleanup(retiring.session, retiring.result, key);
    }
  }

  return { activate, retire };
}
