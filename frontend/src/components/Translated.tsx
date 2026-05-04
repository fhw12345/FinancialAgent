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
import { useTranslated } from "../hooks/useTranslated";

interface Props {
  text: string | null | undefined;
  as?: ElementType;
  className?: string;
  /** Optional renderer if you need to wrap the text (e.g. markdown). */
  render?: (translated: string) => ReactNode;
}

export function Translated({ text, as: Tag = "span", className, render }: Props) {
  const { text: shown, isLoading } = useTranslated(text);
  const content = render ? render(shown) : shown;
  return (
    <Tag
      className={className}
      // Subtle hint that translation is in flight — opacity dip, no spinner
      // so we don't disrupt long lists of decisions all updating at once.
      style={isLoading ? { opacity: 0.7 } : undefined}
    >
      {content}
    </Tag>
  );
}
