type RealtimeEvent = { id: number; game_id: string };

export function createRealtimeCursor(maxSeenIds = 512) {
  const limit = Math.max(1, Math.floor(maxSeenIds));
  let identity: string | null | undefined;
  let lastEventId = 0;
  const seenIds = new Set<number>();
  const seenOrder: number[] = [];

  function setIdentity(gameId: string | null, userId: string | null): boolean {
    const nextIdentity = gameId && userId ? `${userId}:${gameId}` : null;
    if (identity === nextIdentity) return false;
    identity = nextIdentity;
    lastEventId = 0;
    seenIds.clear();
    seenOrder.length = 0;
    return true;
  }

  function accept<T extends RealtimeEvent>(gameId: string, events: T[]): T[] {
    return events.filter((event) => {
      if (event.game_id !== gameId || event.id <= lastEventId || seenIds.has(event.id)) return false;
      lastEventId = event.id;
      seenIds.add(event.id);
      seenOrder.push(event.id);
      while (seenOrder.length > limit) {
        const retiredId = seenOrder.shift();
        if (retiredId !== undefined) seenIds.delete(retiredId);
      }
      return true;
    });
  }

  return {
    accept,
    afterId: () => lastEventId,
    seenSize: () => seenIds.size,
    setIdentity,
  };
}
