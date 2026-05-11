/**
 * useTranslated — render-time translation for LLM-generated text.
 *
 * Behaviour:
 * - If the active i18n language starts with "en", returns the original text
 *   immediately and never hits the network. Backend prompts are English, so
 *   English UI users see the model output verbatim.
 * - If a non-empty `precomputed` value is supplied (write-time translation
 *   already persisted to MongoDB), returns it immediately and skips the
 *   /api/translate call entirely.
 * - If the source `text` already plausibly looks like the active target
 *   language (CJK content under zh-CN), short-circuits as already-translated.
 *   Guards legacy rows from the pre-English-only era and repaired rows where
 *   the CJK base was copied across, so the UI doesn't fade real Chinese text
 *   through a pointless /api/translate round-trip.
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
import { looksTranslated } from "../utils/i18n/looksTranslated";

const SUPPORTED_TARGETS: ReadonlySet<string> = new Set(["zh-CN"]);

interface Result {
  text: string;
  isLoading: boolean;
  isTranslated: boolean;
}

interface Options {
  /**
   * Server-precomputed translation (e.g. `Message.content_zh`). When the
   * active locale matches and this value is a non-empty string, the hook
   * returns it directly without calling /api/translate. A null or empty
   * string falls through to the lazy translation path.
   */
  precomputed?: string | null;
}

export function useTranslated(
  text: string | null | undefined,
  opts: Options = {}
): Result {
  const { i18n } = useTranslation();
  const lang = i18n.language || "en";
  const isZh = !lang.startsWith("en") && SUPPORTED_TARGETS.has(lang);

  const hasPrecomputed =
    isZh && typeof opts.precomputed === "string" && opts.precomputed.length > 0;

  // If the source text itself already plausibly matches the target language
  // (e.g. legacy rows where Phase 1 emitted Chinese before the English-only
  // pipeline flip, or repaired rows where the CJK base was copied across),
  // skip /api/translate and treat it as already-translated. Without this the
  // hook fires a useless round-trip and renders the text in the opacity-0.7
  // "translating" state — visible to the user as faded Chinese text.
  const alreadyTargetLang =
    isZh && typeof text === "string" && looksTranslated(text, lang);

  const shouldTranslate =
    !!text && isZh && !hasPrecomputed && !alreadyTargetLang;

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
  if (!isZh) return { text, isLoading: false, isTranslated: false };
  if (hasPrecomputed)
    return {
      text: opts.precomputed as string,
      isLoading: false,
      isTranslated: true,
    };
  if (alreadyTargetLang)
    return { text, isLoading: false, isTranslated: true };
  if (query.isLoading) return { text, isLoading: true, isTranslated: false };
  if (query.isError || !query.data)
    return { text, isLoading: false, isTranslated: false };
  return { text: query.data, isLoading: false, isTranslated: true };
}
