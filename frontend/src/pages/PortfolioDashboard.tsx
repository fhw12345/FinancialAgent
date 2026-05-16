/**
 * Portfolio Dashboard.
 *
 * Header (total market value + P/L) → holdings table → settings/analysis →
 * watchlist. The legacy Robinhood-style price chart was removed (v0.21.0):
 * with Alpaca gone we couldn't compute a true historical equity curve, and
 * the synthesized "current holdings × past prices" version was misleading.
 * Sidebar still shows portfolio agent's analysis history.
 */

import { useCallback, useState } from "react";
import { useQueryClient as useReactQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  usePortfolioSummary,
  useHoldings,
  useRefreshHoldingPrices,
} from "../hooks/usePortfolio";
import { usePortfolioChatDetail } from "../hooks/usePortfolioChatDetail";
import { PortfolioSummaryTable } from "../components/portfolio/PortfolioSummaryTable";
import { ResizableColumn } from "../components/portfolio/ResizableColumn";
import { WatchlistPanel } from "../components/portfolio/WatchlistPanel";
import { CronController } from "../components/portfolio/CronController";
import { RecentTransactions } from "../components/portfolio/RecentTransactions";
import { DecisionTracker } from "../components/portfolio/DecisionTracker";
import {
  SettingsPanel,
  usePortfolioSettings,
} from "../components/portfolio/SettingsPanel";
import { AnalysisButtons } from "../components/portfolio/AnalysisButtons";
import { MarketMovers } from "../components/MarketMovers";
import { ChatSidebar } from "../components/chat/ChatSidebar";
import { ChatMessages } from "../components/chat/ChatMessages";
import { formatPL, getPLColor } from "../services/portfolioApi";


export default function PortfolioDashboard() {
  const { t } = useTranslation(["portfolio", "common"]);

  // Chat sidebar state
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false); // Start open
  const [selectedDate, setSelectedDate] = useState<string | null>(null); // Date filter for chat history
  const [messageSortOrder, setMessageSortOrder] = useState<"newest" | "oldest">(
    "newest",
  ); // Sort order for messages in modal
  const [analysisType, setAnalysisType] = useState<string>(""); // Analysis type filter ("individual" or "portfolio")

  // Single-user local fork — always treated as admin.
  const isAdmin = true;

  const {
    data: summary,
    isLoading: isLoadingSummary,
    error: summaryError,
  } = usePortfolioSummary();

  const { data: holdings } = useHoldings();

  const currentValue = summary?.total_market_value || 0;
  const totalPL = summary?.total_unrealized_pl || null;
  const totalPLPct = summary?.total_unrealized_pl_pct || null;
  const plColor = getPLColor(totalPL);

  const isLoading = isLoadingSummary;
  const error = summaryError;

  return (
    <div className="min-h-screen bg-white">
      <div className="flex h-screen">
        {/* Left Sidebar - Market Movers & Transactions */}
        <ResizableColumn
          side="left"
          storageKey="portfolio:leftWidth"
          defaultWidth={384}
          className="border-r border-gray-200 bg-gray-50"
        >
          <div className="h-full overflow-y-auto">
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
        </ResizableColumn>

        {/* Main Content Area */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-6xl mx-auto px-3 py-6">
            {/* Error Message */}
            {error && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-700">
                  {error.message || t("portfolio:errors.loadFailed")}
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

            {/* Portfolio Holdings Table — always render so the empty-state
                Add Holding button is reachable when holdings.length === 0. */}
            {summary && holdings && (
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
              <p>{t("portfolio:footer.dataUpdates")}</p>
            </div>
          </div>
        </div>

        {/* Sidebar - Analysis History (Reused Chat Component).
            Collapsed state pinned to 48px; expanded state is user-resizable. */}
        {isSidebarCollapsed ? (
          <div className="flex-shrink-0 w-12 transition-all duration-300 flex flex-col">
            <div className="flex-1 overflow-hidden">
              <ChatSidebar
                activeChatId={activeChatId}
                onChatSelect={setActiveChatId}
                onNewChat={() => {}}
                isCollapsed={isSidebarCollapsed}
                onToggleCollapse={() =>
                  setIsSidebarCollapsed(!isSidebarCollapsed)
                }
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
        ) : (
          <ResizableColumn
            side="right"
            storageKey="portfolio:rightWidth"
            defaultWidth={384}
            className="flex flex-col"
          >
            <div className="flex-1 overflow-hidden h-full">
              <ChatSidebar
                activeChatId={activeChatId}
                onChatSelect={setActiveChatId}
                onNewChat={() => {}}
                isCollapsed={isSidebarCollapsed}
                onToggleCollapse={() =>
                  setIsSidebarCollapsed(!isSidebarCollapsed)
                }
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
          </ResizableColumn>
        )}
      </div>

      {/* Chat Messages Modal - Show when a chat is selected */}
      {activeChatId && !isSidebarCollapsed && (
        <ChatMessagesModal
          chatId={activeChatId}
          onClose={() => setActiveChatId(null)}
          sortOrder={messageSortOrder}
        />
      )}
    </div>
  );
}

// Separate component to handle chat messages modal with data fetching
function ChatMessagesModal({
  chatId,
  onClose,
  sortOrder,
}: {
  chatId: string;
  onClose: () => void;
  sortOrder: "newest" | "oldest";
}) {
  const { t } = useTranslation(["portfolio", "common"]);
  const { data: chatDetail, isLoading } = usePortfolioChatDetail(chatId);

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-gray-900">
            {chatDetail?.chat?.title || t("portfolio:modal.analysisMessages")}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors p-2"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-gray-500">
                {t("portfolio:modal.loadingMessages")}
              </div>
            </div>
          ) : chatDetail?.messages ? (
            <ChatMessages
              messages={chatDetail.messages}
              isAnalysisPending={false}
              chatId={chatId}
              sortOrder={sortOrder}
            />
          ) : (
            <div className="flex items-center justify-center h-full">
              <div className="text-gray-500">
                {t("portfolio:modal.noMessages")}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** Inline composer: settings panel above, analysis triggers below.
 *  When any analysis run completes, refreshes holding prices (which also
 *  bumps `last_price_update`) and invalidates decisions so the
 *  DecisionTracker, PortfolioSummaryTable and the "Last updated" header
 *  reflect freshly-fetched values.
 */
function PortfolioSettingsAndAnalysis() {
  const settings = usePortfolioSettings();
  const ready = !!settings.data;
  const qc = useReactQueryClient();
  const refreshMut = useRefreshHoldingPrices();
  const refreshPrices = refreshMut.mutate;
  // useCallback is mandatory — AnalysisButtons has a useEffect with
  // onRunComplete in its deps. A fresh inline closure each render would
  // re-trigger the effect, mutate(), bump refreshMut.isPending, re-render
  // this parent, recreate the closure → infinite loop. mutate() is a stable
  // function reference across renders; the wrapping mutation object is not.
  const onRunComplete = useCallback(() => {
    qc.invalidateQueries({ queryKey: ["decisions"] });
    refreshPrices();
  }, [qc, refreshPrices]);
  return (
    <>
      <SettingsPanel />
      <AnalysisButtons settingsReady={ready} onRunComplete={onRunComplete} />
    </>
  );
}
