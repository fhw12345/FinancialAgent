import { useState, useMemo, useCallback, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { agentRunService, chatService } from "../services/api";
import { marketService, TimeInterval } from "../services/market";
import { useChatManager } from "./chat/useChatManager";
import { useAnalysis, useButtonAnalysis } from "./chat/useAnalysis";
import { ChatMessages } from "./chat/ChatMessages";
import { ChatInput } from "./chat/ChatInput";
import { ChartPanel } from "./chat/ChartPanel";
import { ChatSidebar } from "./chat/ChatSidebar";
import { useChatRestoration } from "../hooks/useChatRestoration";
import { useUIStateSync } from "../hooks/useUIStateSync";
import type { FibonacciMetadata } from "../utils/analysisMetadataExtractor";
import {
  calculateDateRangeForSymbol,
  getPeriodForInterval,
} from "../utils/dateRangeCalculator";
import type {
  AgentFlow,
  DeepStreamEvent,
  ResponseStreamModeEvent,
  RunStateEvent,
  RouteSelectedEvent,
  SymbolCandidate,
} from "../types/api";
import {
  useDeepAccordionState,
  DeepAgentAccordion,
  mapDeepEventToAction,
} from "./chat/deep";
import { parseBackendMessage, replayDeepEvents } from "../utils/messageParser";

function routeLabelKey(flow: AgentFlow): string {
  if (flow === "v2") return "chat:routing.flows.v2";
  if (flow === "v4-deep") return "chat:routing.flows.v4Deep";
  return "chat:routing.flows.v3";
}

function routeBadgeClass(flow: AgentFlow): string {
  if (flow === "v2") return "bg-purple-100 text-purple-800";
  if (flow === "v4-deep") return "bg-amber-100 text-amber-800";
  return "bg-blue-100 text-blue-800";
}

function routeReasonKey(reasonCode: string): string {
  const keys: Record<string, string> = {
    deep_financial_request: "chat:routing.reasons.deepFinancialRequest",
    live_data_or_tool_request: "chat:routing.reasons.liveDataOrToolRequest",
    selected_symbol_analysis: "chat:routing.reasons.selectedSymbolAnalysis",
    explicit_symbol_analysis: "chat:routing.reasons.explicitSymbolAnalysis",
    concept_explanation: "chat:routing.reasons.conceptExplanation",
    classifier_v2: "chat:routing.reasons.classifier",
    classifier_v3: "chat:routing.reasons.classifier",
    classifier_v4_deep: "chat:routing.reasons.classifier",
    classifier_error_fallback: "chat:routing.reasons.classifierFallback",
    explicit_override: "chat:routing.reasons.explicitOverride",
    restored_deep: "chat:routing.reasons.restoredDeep",
  };
  return keys[reasonCode] ?? "chat:routing.reasons.default";
}

export function EnhancedChatInterface() {
  const { t } = useTranslation(["chat", "common"]);
  const [message, setMessage] = useState("");
  const [currentSymbol, setCurrentSymbol] = useState("");
  const [currentCompanyName, setCurrentCompanyName] = useState("");
  const [selectedInterval, setSelectedInterval] = useState<TimeInterval>("1d");
  const [dateRangeStart, setDateRangeStart] = useState("");
  const [dateRangeEnd, setDateRangeEnd] = useState("");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isChartCollapsed, setIsChartCollapsed] = useState(false);

  // Mobile panel visibility (overlays on mobile)
  const [isMobileSidebarVisible, setIsMobileSidebarVisible] = useState(false);
  const [isMobileChartVisible, setIsMobileChartVisible] = useState(false);

  const [routeInfo, setRouteInfo] = useState<RouteSelectedEvent | null>(null);
  const [responseStreamMode, setResponseStreamMode] = useState<
    ResponseStreamModeEvent["mode"] | null
  >(null);
  const [runInfo, setRunInfo] = useState<RunStateEvent | null>(null);

  const { state: deepState, dispatch: deepDispatch } = useDeepAccordionState();

  const handleDeepEvent = useCallback(
    (event: DeepStreamEvent) => {
      const action = mapDeepEventToAction(event);
      if (action) {
        deepDispatch(action);
      }
    },
    [deepDispatch],
  );

  const deepAccordionElement = useMemo(
    () =>
      deepState.status !== "pending" ? (
        <DeepAgentAccordion state={deepState} dispatch={deepDispatch} />
      ) : undefined,
    [deepState, deepDispatch],
  );

  const handleRouteSelected = useCallback((event: RouteSelectedEvent) => {
    setRouteInfo(event);
  }, []);
  const handleStreamMode = useCallback((event: ResponseStreamModeEvent) => {
    setResponseStreamMode(event.mode);
  }, []);
  const handleRunState = useCallback((event: RunStateEvent) => {
    setRunInfo(event);
  }, []);

  // Pagination state for loading older messages
  const [hasMoreMessages, setHasMoreMessages] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  // Memoize selectedDateRange object to prevent recreation on every render
  const selectedDateRange = useMemo(
    () => ({ start: dateRangeStart, end: dateRangeEnd }),
    [dateRangeStart, dateRangeEnd],
  );
  const latestUIStateRef = useRef({
    currentSymbol,
    currentCompanyName,
    selectedInterval,
    selectedDateRange,
  });
  latestUIStateRef.current = {
    currentSymbol,
    currentCompanyName,
    selectedInterval,
    selectedDateRange,
  };

  // Stable setter for date range
  const setSelectedDateRange = useCallback(
    (range: { start: string; end: string }) => {
      setDateRangeStart(range.start);
      setDateRangeEnd(range.end);
    },
    [],
  );

  const { messages, setMessages, chatId, setChatId } = useChatManager();

  const setCreatedChatId = useCallback(
    (newChatId: string) => {
      setChatId(newChatId);

      const persistLatestState = async (attempt = 0): Promise<void> => {
        const latest = latestUIStateRef.current;
        if (!latest.currentSymbol && !latest.selectedDateRange.start) return;
        try {
          await chatService.updateUIState(newChatId, {
            ui_state: {
              current_symbol: latest.currentSymbol || null,
              current_company_name: latest.currentCompanyName || null,
              current_interval: latest.selectedInterval,
              current_date_range: {
                start: latest.selectedDateRange.start || null,
                end: latest.selectedDateRange.end || null,
              },
              active_overlays: {},
            },
          });
        } catch (error) {
          if (attempt < 2) {
            window.setTimeout(
              () => void persistLatestState(attempt + 1),
              500 * (attempt + 1),
            );
            return;
          }
          console.error("Failed to persist initial chat UI state:", error);
        }
      };

      void persistLatestState();
    },
    [setChatId],
  );

  // Chat restoration hook
  const { restoreChat } = useChatRestoration({
    setMessages,
    setCurrentSymbol,
    setCurrentCompanyName,
    setSelectedInterval,
    setSelectedDateRange,
    setChatId,
  });

  // Auto-sync UI state to MongoDB (debounced) - for chat restoration on page reload
  // Note: Symbol is now passed directly in chat request (current_symbol), so no need to flush before send
  useUIStateSync({
    activeChatId: chatId,
    currentSymbol,
    currentCompanyName,
    selectedInterval,
    selectedDateRange,
  });

  // Extract Fibonacci analysis for the current symbol AND timeframe
  const currentFibonacciAnalysis = useMemo(() => {
    if (!currentSymbol) return null;

    // Find the most recent Fibonacci analysis for current symbol AND timeframe
    // Iterate backwards without creating array copy for better performance
    let fibMessage = null;
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i];
      if (
        msg.role === "assistant" &&
        msg.analysis_data &&
        msg.analysis_data.symbol === currentSymbol &&
        msg.analysis_data.fibonacci_levels &&
        msg.analysis_data.timeframe === selectedInterval &&
        msg.analysis_data.start_date === selectedDateRange.start &&
        msg.analysis_data.end_date === selectedDateRange.end
      ) {
        fibMessage = msg;
        break;
      }
    }

    // Type guard to ensure proper typing
    if (!fibMessage?.analysis_data) return null;
    return fibMessage.analysis_data as unknown as FibonacciMetadata;
  }, [
    messages,
    currentSymbol,
    selectedInterval,
    selectedDateRange.start,
    selectedDateRange.end,
  ]);

  // Chat mutation for user messages
  const chatMutation = useAnalysis(
    currentSymbol,
    selectedDateRange,
    setMessages,
    setSelectedDateRange,
    selectedInterval,
    chatId,
    setChatId,
    handleDeepEvent,
    handleRouteSelected,
    handleStreamMode,
    handleRunState,
    setCreatedChatId,
  );

  // Button analysis mutation for quick analysis buttons
  const buttonMutation = useButtonAnalysis(
    currentSymbol,
    selectedDateRange,
    setMessages,
    setSelectedDateRange,
    selectedInterval,
    chatId,
    setChatId,
    setCreatedChatId,
  );

  const priceDataQuery = useQuery({
    queryKey: [
      "priceData",
      currentSymbol,
      selectedInterval,
      selectedDateRange.start,
      selectedDateRange.end,
    ],
    queryFn: () =>
      marketService.getPriceData(currentSymbol, {
        interval: selectedInterval,
        period: getPeriodForInterval(selectedInterval),
        start_date: selectedDateRange.start || undefined,
        end_date: selectedDateRange.end || undefined,
      }),
    enabled: !!currentSymbol,
    placeholderData: (previousData, previousQuery) =>
      previousQuery?.queryKey[1] === currentSymbol ? previousData : undefined,
    staleTime: 30000,
    refetchInterval: 60000,
    retry: false,
  });

  const handleSymbolSelect = useCallback(
    (symbol: string, name: string) => {
      setCurrentSymbol(symbol);
      setCurrentCompanyName(name);

      // Calculate date range for current interval
      const dateRange = calculateDateRangeForSymbol(
        { start: "", end: "" },
        selectedInterval,
        symbol,
      );
      setDateRangeStart(dateRange.start);
      setDateRangeEnd(dateRange.end);
    },
    [selectedInterval],
  );

  const handleSymbolCandidateSelect = useCallback(
    (candidate: SymbolCandidate) => {
      handleSymbolSelect(candidate.symbol, candidate.name);
      setMessage(
        t("chat:clarification.followUp", {
          symbol: candidate.symbol,
        }),
      );
    },
    [handleSymbolSelect, t],
  );

  const handleIntervalChange = useCallback(
    (interval: TimeInterval) => {
      setSelectedInterval(interval);

      const dateRange = calculateDateRangeForSymbol(
        { start: "", end: "" },
        interval,
        currentSymbol,
      );
      setDateRangeStart(dateRange.start);
      setDateRangeEnd(dateRange.end);
    },
    [currentSymbol],
  );

  const handleDateRangeSelect = useCallback(
    (startDate: string, endDate: string) => {
      setDateRangeStart(startDate);
      setDateRangeEnd(endDate);
    },
    [],
  );

  const handleQuickAnalysis = useCallback(
    (
      type:
        | "fibonacci"
        | "company_overview"
        | "macro"
        | "stochastic"
        | "news_sentiment"
        | "cash_flow"
        | "balance_sheet"
        | "market_movers",
    ) => {
      // Route all analysis types to direct API (< 1 second response, no LLM cost)
      // User message is now handled by useButtonAnalysis.onSuccess
      buttonMutation.mutate(type);
    },
    [buttonMutation],
  );

  // Old complex pattern matching logic removed
  const handleSendMessage = useCallback(() => {
    if (!message.trim()) return;
    // Request deduplication: Prevent concurrent agent invocations
    if (chatMutation.isPending) {
      console.log("⏭️ Skipping message submit: request already in progress");
      return;
    }

    setRouteInfo(null);
    setResponseStreamMode(null);
    setRunInfo(null);
    deepDispatch({ type: "RESET" });
    chatMutation.mutate(message);
    setMessage("");
  }, [message, chatMutation, deepDispatch]);

  const handleCancelMessage = useCallback(() => {
    chatMutation.cancelActiveRequest();
    deepDispatch({ type: "CANCEL" });
  }, [chatMutation, deepDispatch]);

  const isRestoringRef = useRef(false);
  const [isRestoringChat, setIsRestoringChat] = useState(false);

  const handleChatSelect = useCallback(
    async (selectedChatId: string) => {
      // Prevent concurrent restoration requests
      if (isRestoringRef.current) {
        console.log("Skipping chat select: restoration in progress");
        return;
      }

      isRestoringRef.current = true;
      setIsRestoringChat(true);
      setChatId(selectedChatId);
      setResponseStreamMode(null);
      setRunInfo(null);
      try {
        deepDispatch({ type: "RESET" });

        const restoredMessages = await restoreChat(selectedChatId);
        setHasMoreMessages(true);

        // Replay deep events from the most recent deep analysis message
        if (restoredMessages) {
          const hasDeep = replayDeepEvents(
            restoredMessages,
            mapDeepEventToAction,
            deepDispatch,
          );
          const latestRoute = [...restoredMessages]
            .reverse()
            .find((msg) => msg.route_selected)?.route_selected;
          setRouteInfo(
            latestRoute ??
              (hasDeep
                ? {
                    type: "route_selected",
                    flow: "v4-deep",
                    source: "rule",
                    reason_code: "restored_deep",
                  }
                : null),
          );
          const latestRunMessage = [...restoredMessages]
            .reverse()
            .find((msg) => msg.run_id && msg.run_status);
          const messageRunInfo = latestRunMessage
            ? {
                type: "run_state" as const,
                run_id: latestRunMessage.run_id as string,
                status: latestRunMessage.run_status as RunStateEvent["status"],
              }
            : null;
          try {
            const [latestRun] = await agentRunService.listChatRuns(
              selectedChatId,
              1,
            );
            setRunInfo(
              latestRun
                ? {
                    type: "run_state",
                    run_id: latestRun.run_id,
                    status: latestRun.status,
                    execution_mode: latestRun.execution_mode ?? undefined,
                  }
                : messageRunInfo,
            );
          } catch {
            setRunInfo(messageRunInfo);
          }
        } else {
          setChatId(null);
        }
      } finally {
        isRestoringRef.current = false;
        setIsRestoringChat(false);
      }
    },
    [restoreChat, deepDispatch, setChatId],
  );

  const handleNewChat = useCallback(() => {
    setMessages([]);
    setChatId(null);
    setCurrentSymbol("");
    setCurrentCompanyName("");
    setDateRangeStart("");
    setDateRangeEnd("");
    setHasMoreMessages(false); // Reset pagination
    deepDispatch({ type: "RESET" }); // Reset deep accordion state
    setRouteInfo(null);
    setResponseStreamMode(null);
    setRunInfo(null);
  }, [setMessages, setChatId, deepDispatch]);

  const handleLoadMore = useCallback(async () => {
    if (!chatId || isLoadingMore) return;

    setIsLoadingMore(true);

    // Capture scroll position BEFORE loading
    const scrollContainer = document.querySelector("[data-chat-scroll]");
    const prevScrollHeight = scrollContainer?.scrollHeight ?? 0;

    try {
      const { chatService } = await import("../services/api");
      const currentOffset = messages.length;
      const chatDetail = await chatService.getChatDetail(
        chatId,
        50,
        currentOffset,
      );

      if (chatDetail.messages.length === 0) {
        setHasMoreMessages(false);
        return;
      }

      const olderMessages = chatDetail.messages.map(parseBackendMessage);

      // Only replay deep events when the accordion is not already populated.
      // Once a deep analysis accordion is loaded (status !== "pending"), we
      // must NOT overwrite it with events from older paginated messages —
      // that would replace the most-recent analysis with a stale one.
      if (deepState.status === "pending") {
        replayDeepEvents(olderMessages, mapDeepEventToAction, deepDispatch);
      }

      setMessages((prev) => [...olderMessages, ...prev]);
      setHasMoreMessages(chatDetail.messages.length === 50);

      // Restore scroll position AFTER React renders new messages (double rAF ensures DOM flush)
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (scrollContainer) {
            const newScrollHeight = scrollContainer.scrollHeight;
            scrollContainer.scrollTop += newScrollHeight - prevScrollHeight;
          }
        });
      });
    } catch (error) {
      console.error("❌ Failed to load more messages:", error);
    } finally {
      setIsLoadingMore(false);
    }
  }, [
    chatId,
    messages.length,
    isLoadingMore,
    setMessages,
    deepDispatch,
    deepState.status,
  ]);

  return (
    <div className="bg-white overflow-hidden max-h-screen">
      {/* Desktop: CSS Grid with fixed sidebar + flexible chat + narrow chart */}
      {/* Mobile: Flex column with overlays */}
      <div className="mx-auto">
        <div className="relative">
          <div
            className="flex flex-col lg:grid lg:gap-0 h-[calc(100vh-5rem)]"
            style={{
              gridTemplateColumns: `${isSidebarCollapsed ? "48px" : "240px"} minmax(500px, 1fr) ${isChartCollapsed ? "48px" : "minmax(500px, 800px)"}`,
            }}
          >
            {/* Chat History Sidebar - Mobile: overlay, Desktop: fixed 240px column */}
            <div
              className={`${
                isMobileSidebarVisible
                  ? "absolute top-0 left-0 z-20 h-full w-64 bg-white shadow-2xl"
                  : "hidden"
              } lg:block lg:relative lg:z-0 lg:w-auto lg:border-r lg:border-gray-300 lg:h-full lg:overflow-hidden`}
            >
              <ChatSidebar
                activeChatId={chatId}
                onChatSelect={(id) => void handleChatSelect(id)}
                onNewChat={handleNewChat}
                isCollapsed={isSidebarCollapsed}
                onToggleCollapse={() =>
                  setIsSidebarCollapsed(!isSidebarCollapsed)
                }
              />
            </div>

            {/* Mobile sidebar backdrop */}
            {isMobileSidebarVisible && (
              <div
                role="button"
                tabIndex={0}
                className="absolute inset-0 bg-black/50 z-10 lg:hidden"
                onClick={() => setIsMobileSidebarVisible(false)}
                onKeyDown={(e) => {
                  if (e.key === "Escape" || e.key === "Enter") {
                    setIsMobileSidebarVisible(false);
                  }
                }}
                aria-label="Close sidebar"
              />
            )}
            {/* Chat Panel - Mobile: primary full-width, Desktop: flexible middle column */}
            <div className="flex flex-col h-full w-full lg:w-auto lg:min-w-[500px] border-r border-gray-300 relative bg-gray-50 overflow-hidden">
              {/* Mobile toggle buttons - only show when panels are closed */}
              {!isMobileChartVisible && (
                <div className="flex lg:hidden absolute top-2 left-2 right-2 z-10 gap-2">
                  <button
                    onClick={() =>
                      setIsMobileSidebarVisible(!isMobileSidebarVisible)
                    }
                    className="px-3 py-1.5 bg-white/90 backdrop-blur-sm border border-gray-200 rounded-lg shadow-sm text-xs font-medium text-gray-700 hover:bg-gray-50"
                  >
                    {isMobileSidebarVisible
                      ? t("chat:mobile.hideSidebar")
                      : t("chat:mobile.showChats")}
                  </button>
                  <button
                    onClick={() => setIsMobileChartVisible(true)}
                    className="ml-auto px-3 py-1.5 bg-white/90 backdrop-blur-sm border border-gray-200 rounded-lg shadow-sm text-xs font-medium text-gray-700 hover:bg-gray-50"
                  >
                    {t("chat:mobile.showChart")}
                  </button>
                </div>
              )}

              {/* Add padding-top to prevent toggle buttons from covering messages */}
              <div className="pt-12 lg:pt-0 flex flex-col h-full">
                <ChatMessages
                  messages={messages}
                  isAnalysisPending={
                    isRestoringChat ||
                    chatMutation.isPending ||
                    buttonMutation.isPending
                  }
                  chatId={chatId}
                  onLoadMore={handleLoadMore}
                  hasMore={hasMoreMessages}
                  isLoadingMore={isLoadingMore}
                  deepAccordion={deepAccordionElement}
                  onSymbolCandidateSelect={handleSymbolCandidateSelect}
                />

                {/* Automatic flow routing status */}
                <div className="flex-shrink-0 px-4 py-2 border-t border-gray-100 bg-gray-50/50">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-gray-600 font-medium">
                      {t("chat:routing.label")}:
                    </span>
                    {routeInfo ? (
                      <>
                        <span
                          className={`rounded-full px-2.5 py-1 text-xs font-semibold ${routeBadgeClass(routeInfo.flow)}`}
                        >
                          {t(routeLabelKey(routeInfo.flow))}
                        </span>
                        <span className="text-xs text-gray-500">
                          {t(routeReasonKey(routeInfo.reason_code))}
                        </span>
                      </>
                    ) : (
                      <span className="text-xs text-gray-500">
                        {t("chat:routing.waiting")}
                      </span>
                    )}
                    {responseStreamMode && (
                      <span
                        data-testid="response-stream-mode"
                        data-stream-mode={responseStreamMode}
                        className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                          responseStreamMode === "model_tokens"
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-amber-100 text-amber-700"
                        }`}
                      >
                        {responseStreamMode === "model_tokens"
                          ? t("chat:streaming.modelTokens")
                          : t("chat:streaming.buffered")}
                      </span>
                    )}
                    {runInfo && (
                      <span
                        data-testid="run-state"
                        data-run-id={runInfo.run_id}
                        data-run-status={runInfo.status}
                        className="rounded-full bg-slate-200 px-2.5 py-1 font-mono text-xs text-slate-700"
                        title={runInfo.run_id}
                      >
                        {runInfo.status} · {runInfo.run_id.slice(-8)}
                      </span>
                    )}
                  </div>
                </div>

                <ChatInput
                  message={message}
                  setMessage={setMessage}
                  onSendMessage={handleSendMessage}
                  onCancelMessage={handleCancelMessage}
                  isPending={
                    isRestoringChat ||
                    chatMutation.isPending ||
                    buttonMutation.isPending
                  }
                  canCancel={chatMutation.isPending}
                  currentSymbol={currentSymbol}
                />
              </div>
            </div>

            {/* Chart Panel - Mobile: slide-in drawer (80% width), Desktop: fixed column */}
            <div
              className={`${
                isMobileChartVisible
                  ? "absolute top-0 right-0 z-30 h-full w-4/5 bg-white shadow-2xl transform transition-transform duration-300"
                  : "hidden lg:block lg:relative lg:z-0 lg:w-auto lg:h-full lg:overflow-hidden"
              }`}
            >
              {/* Mobile close button for chart panel */}
              {isMobileChartVisible && (
                <div className="lg:hidden absolute top-2 left-2 right-2 z-40 flex justify-between items-center px-2">
                  <button
                    onClick={() => setIsMobileChartVisible(false)}
                    className="px-4 py-2 bg-white/95 backdrop-blur-sm border border-gray-300 rounded-lg shadow-lg text-sm font-medium text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                  >
                    {t("chat:mobile.backToChat")}
                  </button>
                  <button
                    onClick={() => setIsMobileChartVisible(false)}
                    className="w-9 h-9 bg-white/95 backdrop-blur-sm border border-gray-300 rounded-lg shadow-lg text-gray-700 hover:bg-gray-50 flex items-center justify-center font-semibold"
                    aria-label="Close chart"
                  >
                    ✕
                  </button>
                </div>
              )}

              <ChartPanel
                currentSymbol={currentSymbol}
                currentCompanyName={currentCompanyName}
                priceDataQuery={priceDataQuery}
                selectedInterval={selectedInterval}
                selectedDateRange={selectedDateRange}
                analysisMutation={buttonMutation}
                fibonacciAnalysis={currentFibonacciAnalysis}
                handleSymbolSelect={handleSymbolSelect}
                handleIntervalChange={handleIntervalChange}
                handleDateRangeSelect={handleDateRangeSelect}
                handleQuickAnalysis={handleQuickAnalysis}
                isCollapsed={isChartCollapsed}
                onToggleCollapse={() => setIsChartCollapsed(!isChartCollapsed)}
              />
            </div>

            {/* Mobile chart backdrop - allows clicking to close */}
            {isMobileChartVisible && (
              <div
                role="button"
                tabIndex={0}
                className="absolute inset-0 bg-black/60 z-20 lg:hidden"
                onClick={() => setIsMobileChartVisible(false)}
                onKeyDown={(e) => {
                  if (e.key === "Escape" || e.key === "Enter") {
                    setIsMobileChartVisible(false);
                  }
                }}
                aria-label="Close chart"
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
