export type SessionBootstrapFailure = "none" | "unauthorized" | "transient";
export type SessionBootstrapDecision = "restore" | "reonboard" | "retry";
export type RestoredSessionDestination = "home" | "invites";

export function decideSessionBootstrap(
  hasStoredUserId: boolean,
  hasStoredToken: boolean,
  failure: SessionBootstrapFailure = "none",
): SessionBootstrapDecision {
  if (!hasStoredUserId || !hasStoredToken) return "reonboard";
  if (failure === "unauthorized") return "reonboard";
  if (failure === "transient") return "retry";
  return "restore";
}

export function restoredSessionDestination(hasPendingInvite: boolean): RestoredSessionDestination {
  return hasPendingInvite ? "invites" : "home";
}
