import { Building2, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  ClarificationRequiredEvent,
  SymbolCandidate,
} from "../../types/api";

interface SymbolClarificationCardProps {
  clarification: ClarificationRequiredEvent;
  onSelectCandidate?: (candidate: SymbolCandidate) => void;
}

export function SymbolClarificationCard({
  clarification,
  onSelectCandidate,
}: SymbolClarificationCardProps) {
  const { t } = useTranslation(["chat"]);

  return (
    <section
      data-testid="symbol-clarification"
      className="rounded-xl border border-amber-200 bg-amber-50 p-4"
      aria-label={t("chat:clarification.title")}
    >
      <div className="flex items-start gap-3">
        <Search className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-700" />
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-amber-950">
            {t("chat:clarification.title")}
          </h3>
          <p className="mt-1 text-sm text-amber-900">{clarification.message}</p>

          {clarification.candidates.length > 0 ? (
            <div className="mt-3 grid gap-2">
              {clarification.candidates.map((candidate) => (
                <button
                  key={candidate.symbol}
                  type="button"
                  data-testid={`symbol-candidate-${candidate.symbol}`}
                  onClick={() => onSelectCandidate?.(candidate)}
                  className="flex w-full items-center gap-3 rounded-lg border border-amber-200 bg-white px-3 py-2 text-left transition-colors hover:border-blue-300 hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <Building2 className="h-4 w-4 flex-shrink-0 text-gray-500" />
                  <span className="min-w-0 flex-1">
                    <span className="block font-mono text-sm font-bold text-gray-900">
                      {candidate.symbol}
                    </span>
                    <span className="block truncate text-xs text-gray-600">
                      {candidate.name}
                      {candidate.exchange ? ` · ${candidate.exchange}` : ""}
                    </span>
                  </span>
                  <span className="text-xs font-medium text-blue-700">
                    {t("chat:clarification.select")}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-sm text-amber-900">
              {t("chat:clarification.searchGuidance")}
            </p>
          )}

          {clarification.candidates.length > 0 && (
            <p
              data-testid="symbol-search-another"
              className="mt-3 text-xs text-amber-800"
            >
              {t("chat:clarification.searchAnother")}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
