import { z } from "zod";
import { apiClient } from "./api";

const modelSchema = z.object({
  id: z.string(),
  name: z.string(),
  max_output_tokens: z.number().int().positive(),
  api: z.enum(["openai-responses", "openai-completions"]).optional(),
  vendor: z.string().optional(),
});
export const copilotStatusSchema = z.object({
  provider_enabled: z.boolean(),
  github_authorized: z.boolean(),
  authenticated: z.boolean(),
  selected_model: z.string().nullable(),
  models: z.array(modelSchema),
  role_models: z.record(z.string()).optional(),
  routing_revision: z.number().int().nonnegative().optional(),
  roles: z.array(z.object({ id: z.string(), label: z.string() })).optional(),
  recommended_role_models: z.record(z.string()).optional(),
  login: z
    .object({
      attempt_id: z.string(),
      state: z.enum(["pending", "denied", "expired", "failed"]),
      user_code: z.string(),
      verification_uri: z.literal("https://github.com/login/device"),
      expires_at: z.number().finite(),
      interval: z.number().positive(),
    })
    .nullable(),
});
export type CopilotStatus = z.infer<typeof copilotStatusSchema>;
export type CopilotAction =
  "status" | "login" | "poll" | "models" | "model" | "logout" | "routing";

const headers = { "X-Financial-Agent-Local": "1" };

export async function copilotAction(
  action: CopilotAction,
  payload: Record<string, unknown> = {},
  signal?: AbortSignal,
): Promise<CopilotStatus> {
  const url = `/api/llm/copilot/${action}`;
  const response =
    action === "status"
      ? await apiClient.get<unknown>(url, { signal })
      : await apiClient.post<unknown>(url, payload, { signal, headers });
  return copilotStatusSchema.parse(response.data);
}

export async function testCopilot(
  signal?: AbortSignal,
  options: { model_id?: string; role?: string } = {},
): Promise<string> {
  const response = await apiClient.post<unknown>(
    "/api/llm/copilot/test",
    options,
    {
      signal,
      headers,
      timeout: 90000,
    },
  );
  return z
    .object({
      connected: z.literal(true),
      model: z.string(),
      protocol: z.enum(["openai-responses", "openai-completions"]),
    })
    .parse(response.data).model;
}

export function copilotError(error: unknown): string {
  const parsed = z
    .object({ response: z.object({ data: z.object({ detail: z.string() }) }) })
    .safeParse(error);
  return parsed.success
    ? parsed.data.response.data.detail
    : "Copilot request failed. Please retry or check backend connectivity.";
}
