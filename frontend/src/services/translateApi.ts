/**
 * Translation API client.
 *
 * Calls backend /api/translate to translate LLM-generated English content
 * (decision reasoning, research summaries, debate text, verdicts) into the
 * user's UI language. Backend caches per text+lang for 1 day, so repeated
 * page loads of the same content do not incur LLM cost.
 */

import { apiClient } from "./api";

export type TargetLang = "zh-CN";

export interface TranslateRequest {
  texts: string[];
  target_lang: TargetLang;
}

export interface TranslateResponse {
  translations: string[];
}

export async function translateBatch(
  texts: string[],
  targetLang: TargetLang
): Promise<string[]> {
  if (texts.length === 0) return [];
  const { data } = await apiClient.post<TranslateResponse>("/api/translate", {
    texts,
    target_lang: targetLang,
  } as TranslateRequest);
  return data.translations;
}
