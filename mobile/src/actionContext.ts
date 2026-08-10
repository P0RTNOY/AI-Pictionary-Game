export type ActionContext = {
  epoch: number;
  userId: string | null;
  gameId: string | null;
  roundId: string | null;
};

export function isActionContextCurrent(captured: ActionContext, current: ActionContext, appActive: boolean): boolean {
  return (
    appActive &&
    captured.epoch === current.epoch &&
    captured.userId === current.userId &&
    captured.gameId === current.gameId &&
    captured.roundId === current.roundId
  );
}

export function createActionContextGuard(
  captured: ActionContext,
  current: () => ActionContext,
  appActive: () => boolean,
): (signal?: AbortSignal) => boolean {
  return (signal) => !signal?.aborted && isActionContextCurrent(captured, current(), appActive());
}
