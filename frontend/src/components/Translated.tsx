/**
 * <Translated text={...} /> — drop-in replacement for `{text}` JSX expressions
 * that should be translated when the UI is in a non-English locale.
 *
 * Usage:
 *   <Translated text={decision.reasoning} />
 *   <Translated text={summary} as="span" />
 *
 * Renders the original English while the translation is in flight (no flicker,
 * no layout shift). When translated, shows the localized text in place. On
 * translation error, silently falls back to the original.
 */

import { type ElementType, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useTranslated } from "../hooks/useTranslated";
import { looksTranslated } from "../utils/i18n/looksTranslated";

interface Props {
  text: string | null | undefined;
  /**
   * Server-precomputed translation (e.g. `Message.content_zh`). When set
   * to a non-empty string and the active locale matches, the hook returns
   * it immediately without calling /api/translate.
   */
  precomputed?: string | null;
  as?: ElementType;
  className?: string;
  /** Optional renderer if you need to wrap the text (e.g. markdown). */
  render?: (translated: string) => ReactNode;
}

export function Translated({ text, precomputed, as: Tag = "span", className, render }: Props) {
  const { i18n } = useTranslation();
  // Defensive guard against a backend bug that occasionally writes English
  // into `_zh` fields (DashScope reverse-translation regression). If the
  // precomputed value doesn't look like the active target language, drop it
  // and fall through to lazy translation rather than render the inverted
  // string. See feedback_translation_no_english_flash.md.
  const safePrecomputed = looksTranslated(precomputed, i18n.language || "en")
    ? precomputed
    : null;
  const { text: shown, isLoading } = useTranslated(text, {
    precomputed: safePrecomputed,
  });
  const content = render ? render(shown) : shown;
  return (
    <Tag
      className={className}
      // Subtle hint that translation is in flight — opacity dip, no spinner
      // so we don't disrupt long lists of decisions all updating at once.
      // `data-translating` is the contract the e2e no-English-flash spec
      // asserts on while the lazy translation request is open.
      data-translating={isLoading ? "true" : undefined}
      style={isLoading ? { opacity: 0.7 } : undefined}
    >
      {content}
    </Tag>
  );
}
