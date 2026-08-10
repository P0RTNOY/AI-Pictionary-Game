export function clampPersistedClueCount(value: number, availableClues: number): number {
  const maximum = Math.max(1, Math.floor(availableClues));
  const persisted = Number.isFinite(value) ? Math.floor(value) : 1;
  return Math.min(maximum, Math.max(1, persisted));
}
