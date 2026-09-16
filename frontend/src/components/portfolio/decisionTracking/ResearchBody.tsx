import { useTranslation } from "react-i18next";
import { useTranslated } from "../../../hooks/useTranslated";
import { looksTranslated } from "../../../utils/i18n/looksTranslated";
import { AssistantMarkdown } from "../../chat/AssistantMarkdown";

export function ResearchBody({
  text,
  precomputed,
}: {
  text: string;
  precomputed: string | null;
}) {
  const { i18n } = useTranslation();
  const safe = looksTranslated(precomputed, i18n.language || "en")
    ? precomputed
    : null;
  const { text: shown, isLoading } = useTranslated(text, { precomputed: safe });
  return (
    <div
      className="markdown-content text-sm max-w-none"
      data-translating={isLoading ? "true" : undefined}
      style={isLoading ? { opacity: 0.7 } : undefined}
    >
      <AssistantMarkdown>{shown}</AssistantMarkdown>
    </div>
  );
}
