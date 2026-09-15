import { z } from "zod";
import { apiClient } from "./api";

const modelSchema = z.object({
  id: z.string(),
  name: z.string(),
  max_output_tokens: z.number().int().positive(),
});
export const copilotStatusSchema = z.object({
  provider_enabled: z.boolean(),
  github_authorized: z.boolean(),
  authenticated: z.boolean(),
  selected_model: z.string().nullable(),
  models: z.array(modelSchema),
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
  "status" | "login" | "poll" | "models" | "model" | "logout";

const headers = { "X-Financial-Agent-Local": "1" };

export async function copilotAction(
  action: CopilotAction,
  payload: Record<string, string> = {},
  signal?: AbortSignal,
): Promise<CopilotStatus> {
  const url = `/api/llm/copilot/${action}`;
  const response =
    action === "status"
      ? await apiClient.get<unknown>(url, { signal })
      : await apiClient.post<unknown>(url, payload, { signal, headers });
  return copilotStatusSchema.parse(response.data);
}

export async function testCopilot(signal?: AbortSignal): Promise<string> {
  const response = await apiClient.post<unknown>(
    "/api/llm/copilot/test",
    {},
    {
      signal,
      headers,
      timeout: 60000,
    },
  );
  return z
    .object({
      connected: z.literal(true),
      model: z.string(),
      protocol: z.literal("openai-responses"),
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
