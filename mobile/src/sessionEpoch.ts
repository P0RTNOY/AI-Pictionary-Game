export type SessionEpoch = {
  capture: () => number;
  activate: () => number;
  retire: () => number;
  isCurrent: (captured: number) => boolean;
  runIfCurrent: <T>(captured: number, apply: () => T) => T | undefined;
};

export function createSessionEpoch(): SessionEpoch {
  let current = 0;
  let active = true;
  return {
    capture: () => current,
    activate: () => {
      active = true;
      return ++current;
    },
    retire: () => {
      active = false;
      return ++current;
    },
    isCurrent: (captured) => active && captured === current,
    runIfCurrent: (captured, apply) => (active && captured === current ? apply() : undefined),
  };
}
