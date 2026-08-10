export type RealtimeFailurePolicy = {
  opened: () => RealtimeFailureState;
  healthy: () => RealtimeFailureState;
  failed: () => { failures: number; usePolling: boolean };
  closed: () => { failures: number; usePolling: boolean };
  failures: () => number;
};

type RealtimeFailureState = { failures: number; usePolling: boolean };

export function createRealtimeFailurePolicy(fallbackAfterFailures: number): RealtimeFailurePolicy {
  let failureCount = 0;
  const state = (): RealtimeFailureState => ({
    failures: failureCount,
    usePolling: failureCount >= fallbackAfterFailures,
  });
  const recordFailure = () => {
    failureCount += 1;
    return state();
  };
  return {
    opened: () => {
      // A transport that only opens briefly is not healthy enough to reset failures.
      return state();
    },
    healthy: () => {
      failureCount = 0;
      return state();
    },
    failed: recordFailure,
    closed: recordFailure,
    failures: () => failureCount,
  };
}
