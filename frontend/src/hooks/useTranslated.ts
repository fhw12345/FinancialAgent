/**
 * useTranslated — render-time translation for LLM-generated text.
 *
 * Behaviour:
 * - If the active i18n language starts with "en", returns the original text
 *   immediately and never hits the network. Backend prompts are English, so
 *   English UI users see the model output verbatim.
 * - Otherwise, calls /api/translate and caches the result via TanStack Query.
 *   The backend has its own Redis cache, but the React-Query cache prevents
 *   even one network round-trip per render after the first.
 *
 * Failure mode: returns the original English so the UI never shows a blank
 * field. The hook exposes `isLoading` so callers can render a skeleton or a
 * subtle indicator while the round-trip is in flight (we deliberately do NOT
 * suspend — Decision Tracker rows must remain visible during translation).
 */

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { translateBatch, type TargetLang } from "../services/translateApi";

const SUPPORTED_TARGETS: ReadonlySet<string> = new Set(["zh-CN"]);

interface Result {
  text: string;
  isLoading: boolean;
  isTranslated: boolean;
}

export function useTranslated(text: string | null | undefined): Result {
  const { i18n } = useTranslation();
  const lang = i18n.language || "en";
  const shouldTranslate =
    !!text && !lang.startsWith("en") && SUPPORTED_TARGETS.has(lang);

  const query = useQuery({
    queryKey: ["translate", lang, text],
    queryFn: async () => {
      const out = await translateBatch([text as string], lang as TargetLang);
      return out[0] ?? (text as string);
    },
    enabled: shouldTranslate,
    // Translations of fixed English text never change within a session.
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 1h
    retry: 1,
  });

  if (!text) return { text: "", isLoading: false, isTranslated: false };
  if (!shouldTranslate) return { text, isLoading: false, isTranslated: false };
  if (query.isLoading) return { text, isLoading: true, isTranslated: false };
  if (query.isError || !query.data)
    return { text, isLoading: false, isTranslated: false };
  return { text: query.data, isLoading: false, isTranslated: true };
}
