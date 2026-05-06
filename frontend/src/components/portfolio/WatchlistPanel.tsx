/**
 * Watchlist panel for managing tracked stock symbols.
 * Allows users to add/remove symbols for automated monitoring.
 * Shows last analysis time and countdown to next 5-minute analysis cycle.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { SymbolSearch } from "../SymbolSearch";
import {
  useWatchlist,
  useAddToWatchlist,
  useRemoveFromWatchlist,
  useTriggerWatchlistAnalysis,
} from "../../hooks/useWatchlist";
import { formatDate } from "../../utils/timeFormatter";

// Helper to format time ago
function formatTimeAgo(date: Date): string {
  const seconds = Math.floor((new Date().getTime() - date.getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// Calculate next analysis time (next 5-minute mark)
function getNextAnalysisTime(): Date {
  const now = new Date();
  const minutes = now.getMinutes();
  const nextMinute = Math.ceil((minutes + 1) / 5) * 5;
  const next = new Date(now);
  next.setMinutes(nextMinute, 0, 0);
  return next;
}

// Format countdown to next analysis
function formatCountdown(targetDate: Date): string {
  const seconds = Math.floor((targetDate.getTime() - new Date().getTime()) / 1000);
  if (seconds <= 0) return "Analyzing now...";
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

export function WatchlistPanel() {
  const { t, i18n } = useTranslation(['portfolio', 'common']);
  const [newSymbol, setNewSymbol] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: watchlist, isLoading } = useWatchlist();
  const addMutation = useAddToWatchlist();
  const removeMutation = useRemoveFromWatchlist();
  const triggerAnalysisMutation = useTriggerWatchlistAnalysis();

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const symbol = newSymbol.trim().toUpperCase();

    if (!symbol) {
      setError(t('portfolio:watchlistPanel.enterSymbolError'));
      return;
    }

    try {
      await addMutation.mutateAsync({ symbol });
      setNewSymbol("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t('portfolio:errors.loadFailed'));
    }
  };

  const handleRemove = async (watchlistId: string) => {
    try {
      await removeMutation.mutateAsync(watchlistId);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('portfolio:errors.deleteFailed'));
    }
  };

  const handleTriggerAnalysis = async (symbol?: string) => {
    try {
      await triggerAnalysisMutation.mutateAsync(symbol);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('portfolio:errors.loadFailed'));
    }
  };

  // Track which row is currently being analyzed so only that row's spinner
  // shows. The mutation itself is shared, so isPending alone can't distinguish
  // a per-row click from the batch button.
  const [analyzingSymbol, setAnalyzingSymbol] = useState<string | null>(null);
  const handleAnalyzeOne = async (symbol: string) => {
    setAnalyzingSymbol(symbol);
    try {
      await handleTriggerAnalysis(symbol);
    } finally {
      setAnalyzingSymbol(null);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">{t('portfolio:watchlist.title')}</h2>
        <button
          onClick={() => handleTriggerAnalysis()}
          disabled={triggerAnalysisMutation.isPending || !watchlist || watchlist.length === 0}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {triggerAnalysisMutation.isPending && analyzingSymbol === null
            ? t('portfolio:watchlist.analyzing')
            : t('portfolio:watchlistPanel.analyzeNow')}
        </button>
      </div>

      {/* Add Symbol Form */}
      <form onSubmit={handleAdd} className="mb-4">
        <div className="flex gap-2">
          <div className="flex-1">
            <SymbolSearch
              value={newSymbol}
              placeholder={t("portfolio:watchlistPanel.placeholder")}
              onSymbolSelect={(sym) => setNewSymbol(sym)}
            />
          </div>
          <button
            type="submit"
            disabled={addMutation.isPending}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {addMutation.isPending ? t('portfolio:watchlistPanel.adding') : t('common:buttons.add')}
          </button>
        </div>
        {error && (
          <p className="mt-2 text-sm text-red-600">{error}</p>
        )}
      </form>

      {/* Watchlist Items */}
      {isLoading ? (
        <div className="text-center py-4 text-gray-500">{t('common:buttons.loading')}</div>
      ) : watchlist && watchlist.length > 0 ? (
        <div className="space-y-2">
          {watchlist.map((item) => (
            <div
              key={item.watchlist_id}
              className="flex items-center justify-between p-3 bg-gray-50 rounded-md hover:bg-gray-100"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3">
                  <span className="font-medium text-gray-900">{item.symbol}</span>
                  {item.current_price != null && (
                    <span className="font-mono text-sm text-gray-700">
                      ${item.current_price.toFixed(2)}
                    </span>
                  )}
                  {item.last_session && item.last_session !== "regular" && (
                    <span className="inline-flex items-center rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">
                      {t(`portfolio:session.${item.last_session}`)}
                    </span>
                  )}
                </div>
                {item.notes && (
                  <div className="text-sm text-gray-500">{item.notes}</div>
                )}
                <div className="text-xs text-gray-400 mt-1">
                  {t('portfolio:watchlistPanel.added')}: {formatDate(item.added_at, i18n.language)}
                  {item.last_analyzed_at && (
                    <span className="ml-2">
                      • {t('portfolio:watchlistPanel.lastAnalyzed')}: {formatTimeAgo(new Date(item.last_analyzed_at))}
                    </span>
                  )}
                  {!item.last_analyzed_at && (
                    <span className="ml-2 text-amber-600">
                      • {t('portfolio:watchlistPanel.waitingFirstAnalysis')}
                    </span>
                  )}
                </div>
              </div>
              <div className="ml-4 flex items-center gap-1">
                <button
                  onClick={() => handleAnalyzeOne(item.symbol)}
                  disabled={triggerAnalysisMutation.isPending}
                  className="px-2 py-1 text-xs text-blue-600 hover:bg-blue-50 rounded disabled:opacity-50 disabled:cursor-not-allowed"
                  title={t('portfolio:watchlistPanel.analyzeNow')}
                >
                  {analyzingSymbol === item.symbol
                    ? t('portfolio:watchlist.analyzing')
                    : t('portfolio:watchlistPanel.analyzeNow')}
                </button>
                <button
                  onClick={() => handleRemove(item.watchlist_id)}
                  disabled={removeMutation.isPending}
                  className="px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded disabled:opacity-50"
                >
                  {t('portfolio:watchlist.remove')}
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-8 text-gray-500">
          <p>{t('portfolio:watchlistPanel.noSymbols')}</p>
          <p className="text-sm mt-1">{t('portfolio:watchlistPanel.trackPerformance')}</p>
        </div>
      )}
    </div>
  );
}
