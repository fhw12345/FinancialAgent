/** Explicit, paid model-decision requests. Output is a recommendation for human review only. */
import { z } from "zod";
import { apiClient } from "./api";
import { reviewViewSchema, type ReviewRevision } from "./decisionReviews";
import { modelDecisionRecordSchema } from "./modelDecisionSchema";
export const modelDecisionViewSchema = z.object({
  record: modelDecisionRecordSchema,
  review: reviewViewSchema.nullable(),
  review_error: z.string().nullable(),
});
export type ModelDecisionView = z.infer<typeof modelDecisionViewSchema>;
const headers = { "X-Financial-Agent-Local": "1" };
const root = "/api/portfolio/model-decisions";
export async function requestModelDecision(
  version: ReviewRevision,
  assessment_id: string,
): Promise<ModelDecisionView> {
  return modelDecisionViewSchema.parse(
    (
      await apiClient.post<unknown>(
        root,
        {
          ...version,
          assessment_id,
          confirm: true,
          acknowledgment: "uses-model-allowance-recommendation-only-no-trade",
        },
        { headers, timeout: 300000 },
      )
    ).data,
  );
}
export async function getModelDecisions(
  signal?: AbortSignal,
): Promise<ModelDecisionView[]> {
  return z
    .array(modelDecisionViewSchema)
    .parse((await apiClient.get<unknown>(root, { signal })).data);
}
export async function revalidateModelDecision(
  decisionId: string,
  version: ReviewRevision,
): Promise<ModelDecisionView> {
  return modelDecisionViewSchema.parse(
    (
      await apiClient.post<unknown>(
        `${root}/${encodeURIComponent(decisionId)}/review`,
        version,
        { headers, timeout: 120000 },
      )
    ).data,
  );
}
