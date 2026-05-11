/**
 * looksTranslated — defensive guard for server-precomputed translations.
 *
 * The backend stores write-time translations in fields like `full_research_zh`
 * and `reasoning_zh`. A DashScope reverse-translation bug previously caused
 * English text to land in those `_zh` fields, and the UI rendered the English
 * verbatim under a zh-CN locale because `useTranslated` short-circuits when a
 * non-empty `precomputed` value is supplied.
 *
 * This helper inspects the precomputed string and returns true only when the
 * content plausibly matches the requested target language. Callers that get a
 * `false` should drop the precomputed value and fall through to lazy
 * translation (per the no-English-flash contract in
 * `feedback_translation_no_english_flash.md`).
 *
 * Heuristic for `targetLang` starting with "zh":
 *   - At least 3 CJK characters in the text, OR
 *   - ≥1% of non-space characters are CJK.
 *
 * CJK range covers the BMP Unified Ideographs block (U+4E00–U+9FFF) plus
 * Extension A (U+3400–U+4DBF). This catches common Simplified and Traditional
 * Chinese while staying cheap to compute.
 *
 * For non-"zh" targets we return true unconditionally — no guard implemented
 * yet (future work). Empty / whitespace-only input always returns false; an
 * empty string is not a trustworthy translation regardless of locale.
 */

const CJK_CHAR = /[㐀-䶿一-鿿]/g;
const NON_SPACE_CHAR = /\S/g;

export function looksTranslated(
  text: string | null | undefined,
  targetLang: string,
): boolean {
  if (typeof text !== "string") return false;
  if (text.trim().length === 0) return false;

  // Only "zh*" has a real check today. Other targets pass through.
  if (!targetLang || !targetLang.toLowerCase().startsWith("zh")) {
    return true;
  }

  const cjkMatches = text.match(CJK_CHAR);
  const cjkCount = cjkMatches ? cjkMatches.length : 0;
  if (cjkCount >= 3) return true;

  if (cjkCount === 0) return false;

  const nonSpaceMatches = text.match(NON_SPACE_CHAR);
  const nonSpaceCount = nonSpaceMatches ? nonSpaceMatches.length : 0;
  if (nonSpaceCount === 0) return false;

  // ≥1% of visible characters are CJK.
  return cjkCount / nonSpaceCount >= 0.01;
}
