type ProviderRecord = { provider_used?: string | null };

export function artifactProvider(records: ProviderRecord[]): string | null {
  return records.find((record) => record.provider_used)?.provider_used ?? null;
}

export function isMockArtifact(records: ProviderRecord[]): boolean {
  return records.some((record) => record.provider_used === "mock");
}
