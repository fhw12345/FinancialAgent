/** Runtime validation for canonical evidence fields; prose is never a verified fact. */
import { z } from "zod";
import { apiClient } from "./api";
const value = z.union([z.number().finite(), z.string(), z.null()]);
export const evidenceSummarySchema = z.object({
  snapshot_ids: z.array(z.string()),
  dossier_ids: z.array(z.string()),
  errors: z.array(z.string()),
  prose_verification: z.literal("unverified"),
  actionable: z.literal(false),
});
export type EvidenceSummary = z.infer<typeof evidenceSummarySchema>;
const claim = z.object({
  kind: z.enum(["fact", "derived", "hypothesis", "judgment"]),
  symbol: z.string(),
  metric: z.string(),
  value,
  unit: z.string(),
  period: z.string(),
  period_end: z.string().nullable(),
  evidence_ids: z.array(z.string()),
  method: z.string().nullable(),
  text: z.string(),
});
const result = z.object({
  claim_id: z.string(),
  claim,
  status: z.enum(["matches_snapshot", "unverified", "rejected"]),
  reasons: z.array(z.string()),
  evidence_ids: z.array(z.string()),
  computed_value: z.number().finite().nullable(),
});
const dossierSchema = z.object({
  dossier: z.object({
    dossier_id: z.string(),
    snapshot_id: z.string(),
    manifest_hash: z.string(),
    run_id: z.string(),
    symbol: z.string(),
    claims: z.array(result),
    errors: z.array(z.string()),
    prose_verification: z.literal("unverified"),
    actionable: z.literal(false),
  }),
  run_status: z.string().nullable(),
});
export type Dossier = z.infer<typeof dossierSchema>;
const recordSchema = z.object({
  evidence_id: z.string(),
  snapshot_id: z.string(),
  symbol: z.string(),
  instrument_id: z.string(),
  metric: z.string(),
  value,
  unit: z.string(),
  period: z.string(),
  period_start: z.string().nullable(),
  period_end: z.string().nullable(),
  observed_at: z.string().nullable(),
  published_at: z.string().nullable(),
  fetched_at: z.string(),
  provider: z.string(),
  source_uri: z.string().nullable(),
  document_id: z.string().nullable(),
  point_in_time_status: z.enum(["verified", "retrieval_only", "unknown"]),
  quality: z.enum([
    "available",
    "stale",
    "missing",
    "conflicting",
    "unsupported",
  ]),
  payload_hash: z.string(),
  adapter_version: z.string(),
});
export type EvidenceRecord = z.infer<typeof recordSchema>;
const snapshotSchema = z.object({
  snapshot_id: z.string(),
  state: z.literal("sealed"),
  manifest_hash: z.string(),
  coverage: z.record(z.string()),
  conflicts: z.record(z.array(z.string())),
  records_count: z.number().int(),
});
export async function getRunEvidence(
  run: string,
  signal?: AbortSignal,
): Promise<EvidenceSummary | null> {
  return evidenceSummarySchema
    .nullable()
    .parse(
      (
        await apiClient.get<unknown>(
          `/api/portfolio/evidence/runs/${encodeURIComponent(run)}`,
          { signal },
        )
      ).data,
    );
}
export async function getDossier(
  id: string,
  signal?: AbortSignal,
): Promise<Dossier> {
  return dossierSchema.parse(
    (
      await apiClient.get<unknown>(
        `/api/portfolio/evidence/dossiers/${encodeURIComponent(id)}`,
        { signal },
      )
    ).data,
  );
}
export async function getEvidence(
  id: string,
  snapshot: string,
  signal?: AbortSignal,
): Promise<EvidenceRecord> {
  return recordSchema.parse(
    (
      await apiClient.get<unknown>(
        `/api/portfolio/evidence/records/${encodeURIComponent(id)}`,
        { params: { snapshot_id: snapshot }, signal },
      )
    ).data,
  );
}
export async function getManifest(id: string, signal?: AbortSignal) {
  return snapshotSchema.parse(
    (
      await apiClient.get<unknown>(
        `/api/portfolio/evidence/snapshots/${encodeURIComponent(id)}`,
        { params: { limit: 1 }, signal },
      )
    ).data,
  );
}
