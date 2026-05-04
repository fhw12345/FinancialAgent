/**
 * Portfolio Dashboard - Clean Robinhood-style portfolio chart.
 *
 * Shows portfolio value over time with order execution markers.
 * Includes sidebar chat showing portfolio agent's analysis history.
 */

import { useState } from "react";
import { useQueryClient as useReactQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { usePortfolioSummary, usePortfolioHistory, useHoldings } from "../hooks/usePortfolio";
import { usePortfolioChatDetail } from "../hooks/usePortfolioChatDetail";
import { PortfolioChart } from "../components/portfolio/PortfolioChart";
import { PortfolioSummaryTable } from "../components/portfolio/PortfolioSummaryTable";
import { WatchlistPanel } from "../components/portfolio/WatchlistPanel";
import { CronController } from "../components/portfolio/CronController";
import { RecentTransactions } from "../components/portfolio/RecentTransactions";
import { DecisionTracker } from "../components/portfolio/DecisionTracker";
import { SettingsPanel, usePortfolioSettings } from "../components/portfolio/SettingsPanel";
import { AnalysisButtons } from "../components/portfolio/AnalysisButtons";
import { MarketMovers } from "../components/MarketMovers";
import { ChatSidebar } from "../components/chat/ChatSidebar";
import { ChatMessages } from "../components/chat/ChatMessages";
import { formatPL, getPLColor } from "../services/portfolioApi";
import { authStorage } from "../services/authService";

type Period = "1D" | "1M" | "1Y" | "All";

interface AnalysisMarker {
  timestamp: string;
  symbol: string;
  recommendation: string | null;
  summary: string;
}

export default function PortfolioDashboard() {
  const { t } = useTranslation(['portfolio', 'common']);
  const [period, setPeriod] = useState<Period>("1D");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [symbolAnalyses, setSymbolAnalyses] = useState<AnalysisMarker[]>([]);

  // Chat sidebar state
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false); // Start open
  const [selectedDate, setSelectedDate] = useState<string | null>(null); // Date filter for chat history
  const [messageSortOrder, setMessageSortOrder] = useState<"newest" | "oldest">("newest"); // Sort order for messages in modal
  const [analysisType, setAnalysisType] = useState<string>(""); // Analysis type filter ("individual" or "portfolio")

  // Admin check - only admin users can see cron controller
  const currentUser = authStorage.getUser();
  const isAdmin = !!currentUser?.is_admin;

  const {
    data: summary,
    isLoading: isLoadingSummary,
    error: summaryError,
  } = usePortfolioSummary();

  const {
    data: holdings,
    isLoading: isLoadingHoldings,
  } = useHoldings();

  const {
    data: historyData,
    isLoading: isLoadingHistory,
    error: historyError,
    refetch,
  } = usePortfolioHistory(period);

  // Transform API data to chart format
  const chartData =
    historyData?.data_points.map((point) => ({
      time: Math.floor(new Date(point.timestamp).getTime() / 1000), // Convert to Unix seconds
      value: point.value,
    })) || [];

  // Group markers by symbol - show only one marker per symbol
  const markersBySymbol = new Map<string, AnalysisMarker[]>();
  historyData?.markers.forEach((marker) => {
    const existing = markersBySymbol.get(marker.symbol) || [];
    markersBySymbol.set(marker.symbol, [...existing, marker]);
  });

  // Create one marker per symbol (using latest timestamp)
  const chartMarkers = Array.from(markersBySymbol.entries()).map(([symbol, analyses]) => {
    // Sort by timestamp to get latest
    const sortedAnalyses = [...analyses].sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );
    const latestAnalysis = sortedAnalyses[0];

    return {
      time: Math.floor(new Date(latestAnalysis.timestamp).getTime() / 1000),
      position: "aboveBar" as const,
      color: "#3B82F6", // blue-500
      shape: "circle" as const,
      text: `${symbol} (${analyses.length})`, // Show count of analyses
      symbol, // Keep for click handler
      analyses: sortedAnalyses, // All analyses for this symbol
    };
  });

  const currentValue = historyData?.current_value || summary?.total_market_value || 0;
  const totalPL = summary?.total_unrealized_pl || null;
  const totalPLPct = summary?.total_unrealized_pl_pct || null;
  const plColor = getPLColor(totalPL);

  const isLoading = isLoadingSummary || isLoadingHistory;
  const error = summaryError || historyError;

  return (
    <div className="min-h-screen bg-white">
      <div className="flex h-screen">
        {/* Left Sidebar - Market Movers & Transactions */}
        <div className="w-96 border-r border-gray-200 overflow-y-auto bg-gray-50 flex-shrink-0">
          <div className="p-3 space-y-4">
            {/* Market Movers */}
            <MarketMovers
              onTickerClick={(ticker) => {
                console.log("Clicked ticker:", ticker);
              }}
            />

            {/* Recent Transactions */}
            <RecentTransactions />

            {/* AI Decision Tracker — ex-post P&L per decision */}
            <DecisionTracker />
          </div>
        </div>

        {/* Main Content Area */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-6xl mx-auto px-3 py-6">
            {/* Error Message */}
            {error && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-700">
                  {error.message || t('portfolio:errors.loadFailed')}
                </p>
              </div>
            )}

        {/* Portfolio Value Header */}
        <div className="mb-6">
          <div className="text-4xl font-bold text-gray-900 mb-2">
            {isLoading ? (
              <div className="h-10 w-48 bg-gray-200 animate-pulse rounded" />
            ) : (
              `$${currentValue.toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}`
            )}
          </div>

          {/* P/L Display */}
          {!isLoading && totalPL !== null && (
            <div
              className={`text-lg font-medium ${
                plColor === "green"
                  ? "text-green-600"
                  : plColor === "red"
                  ? "text-red-600"
                  : "text-gray-500"
              }`}
            >
              {formatPL(totalPL, totalPLPct)}
            </div>
          )}
        </div>

        {/* Time Period Buttons */}
        <div className="mb-6 flex gap-2">
          {(["1D", "1M", "1Y", "All"] as Period[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                period === p
                  ? "bg-gray-900 text-white"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200"
              }`}
            >
              {p}
            </button>
          ))}

          <button
            onClick={() => {
              void refetch();
            }}
            className="ml-auto px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 transition-colors"
          >
            {t('common:buttons.refresh')}
          </button>
        </div>

        {/* Chart */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          {isLoadingHistory ? (
            <div className="h-96 flex items-center justify-center">
              <div className="text-gray-500">{t('portfolio:chart.loadingChart')}</div>
            </div>
          ) : chartData.length > 0 ? (
            <PortfolioChart
              data={chartData}
              markers={chartMarkers}
              onMarkerClick={(marker: any) => {
                // Open modal with all analyses for this symbol
                setSelectedSymbol(marker.symbol);
                setSymbolAnalyses(marker.analyses);
              }}
            />
          ) : (
            <div className="h-96 flex items-center justify-center">
              <div className="text-center text-gray-500">
                <p>{t('portfolio:chart.noData')}</p>
                <p className="text-sm mt-2">{t('portfolio:chart.addHoldings')}</p>
              </div>
            </div>
          )}
        </div>

            {/* Portfolio Holdings Table */}
            {summary && holdings && holdings.length > 0 && (
              <div className="mt-8">
                <PortfolioSummaryTable holdings={holdings} summary={summary} />
              </div>
            )}

            {/* Settings + AI Analysis triggers */}
            <div className="mt-6">
              <PortfolioSettingsAndAnalysis />
            </div>

            {/* Watchlist Panel */}
            <div className="mt-8">
              <WatchlistPanel />
            </div>

            {/* Cron Controller (Admin Only) - Global System CronJob */}
            {isAdmin && (
              <div className="mt-8">
                <CronController />
              </div>
            )}

            {/* Footer */}
            <div className="mt-8 text-center text-xs text-gray-400">
              <p>{t('portfolio:footer.dataUpdates')}</p>
            </div>
          </div>
        </div>

        {/* Sidebar - Analysis History (Reused Chat Component) */}
        <div className={`flex-shrink-0 transition-all duration-300 ${isSidebarCollapsed ? "w-12" : "w-96"} flex flex-col`}>
          <div className="flex-1 overflow-hidden">
            <ChatSidebar
              activeChatId={activeChatId}
              onChatSelect={setActiveChatId}
              onNewChat={() => {}} // No-op for read-only
              isCollapsed={isSidebarCollapsed}
              onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
              filterUserId="portfolio_agent"
              readOnly={true}
              selectedDate={selectedDate}
              onDateChange={setSelectedDate}
              messageSortOrder={messageSortOrder}
              onMessageSortOrderChange={setMessageSortOrder}
              analysisType={analysisType}
              onAnalysisTypeChange={setAnalysisType}
            />
          </div>
        </div>
      </div>

      {/* Chat Messages Modal - Show when a chat is selected */}
      {activeChatId && !isSidebarCollapsed && <ChatMessagesModal chatId={activeChatId} onClose={() => setActiveChatId(null)} sortOrder={messageSortOrder} />}

      {/* Analysis Modal (legacy - now replaced by sidebar) */}
      {selectedSymbol && (
          <div
            className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
            onClick={() => setSelectedSymbol(null)}
          >
            <div
              className="bg-white rounded-lg max-w-2xl w-full max-h-[80vh] overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Modal Header */}
              <div className="border-b border-gray-200 px-6 py-4 flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-gray-900">{t('portfolio:modal.analysisTitle', { symbol: selectedSymbol })}</h2>
                  <p className="text-sm text-gray-500 mt-1">
                    {symbolAnalyses.length === 1
                      ? t('portfolio:modal.analysisCount', { count: symbolAnalyses.length })
                      : t('portfolio:modal.analysisCountPlural', { count: symbolAnalyses.length })}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedSymbol(null)}
                  className="text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              {/* Modal Body */}
              <div className="overflow-y-auto max-h-[calc(80vh-8rem)] px-6 py-4">
                <div className="space-y-4">
                  {symbolAnalyses.map((analysis, index) => (
                    <div
                      key={`${analysis.timestamp}-${index}`}
                      className="border border-gray-200 rounded-lg p-4 hover:border-blue-300 transition-colors"
                    >
                      {/* Analysis Header */}
                      <div className="flex items-start justify-between mb-3">
                        <div>
                          <div className="text-sm font-medium text-gray-900">
                            {new Date(analysis.timestamp).toLocaleString("en-US", {
                              month: "short",
                              day: "numeric",
                              year: "numeric",
                              hour: "numeric",
                              minute: "2-digit",
                            })}
                          </div>
                          {analysis.recommendation && (
                            <div className="mt-1">
                              <span
                                className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                                  analysis.recommendation.includes("uptrend")
                                    ? "bg-green-100 text-green-800"
                                    : analysis.recommendation.includes("downtrend")
                                    ? "bg-red-100 text-red-800"
                                    : "bg-gray-100 text-gray-800"
                                }`}
                              >
                                {analysis.recommendation}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Analysis Summary */}
                      <div className="text-sm text-gray-600 whitespace-pre-wrap">
                        {analysis.summary}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Modal Footer */}
              <div className="border-t border-gray-200 px-6 py-4">
                <button
                  onClick={() => setSelectedSymbol(null)}
                  className="w-full px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors font-medium"
                >
                  {t('common:buttons.close')}
                </button>
              </div>
            </div>
          </div>
        )}
    </div>
  );
}

// Separate component to handle chat messages modal with data fetching
function ChatMessagesModal({ chatId, onClose, sortOrder }: { chatId: string; onClose: () => void; sortOrder: "newest" | "oldest" }) {
  const { t } = useTranslation(['portfolio', 'common']);
  const { data: chatDetail, isLoading } = usePortfolioChatDetail(chatId);

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-gray-900">
            {chatDetail?.chat?.title || t('portfolio:modal.analysisMessages')}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors p-2"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-gray-500">{t('portfolio:modal.loadingMessages')}</div>
            </div>
          ) : chatDetail?.messages ? (
            <ChatMessages messages={chatDetail.messages} isAnalysisPending={false} chatId={chatId} sortOrder={sortOrder} />
          ) : (
            <div className="flex items-center justify-center h-full">
              <div className="text-gray-500">{t('portfolio:modal.noMessages')}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** Inline composer: settings panel above, analysis triggers below.
 *  When any analysis run completes, invalidates the decisions query so
 *  the DecisionTracker below auto-refreshes.
 */
function PortfolioSettingsAndAnalysis() {
  const settings = usePortfolioSettings();
  const ready = !!settings.data;
  const qc = useReactQueryClient();
  return (
    <>
      <SettingsPanel />
      <AnalysisButtons
        settingsReady={ready}
        onRunComplete={() => {
          qc.invalidateQueries({ queryKey: ["decisions"] });
        }}
      />
    </>
  );
}
