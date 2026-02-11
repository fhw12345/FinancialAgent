import { useState, useMemo, useCallback, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
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
import { getPeriodForInterval, calculateDateRange } from "../utils/dateRangeCalculator";
import type { ModelSettings } from "../types/models";
import type { DeepStreamEvent } from "../types/api";
import { useDeepAccordionState, DeepAgentAccordion, mapDeepEventToAction } from "./chat/deep";

export function EnhancedChatInterface() {
  const { t } = useTranslation(['chat', 'common']);
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

  // LLM Model settings
  const [modelSettings, setModelSettings] = useState<ModelSettings>({
    model: "qwen-plus",
    thinking_enabled: false,
    max_tokens: 3000,
    debug_enabled: false,
  });

  // Agent mode: v3 = Agent (auto tools), v2 = Copilot (manual tools), v4-deep = Deep analysis
  const [agentMode, setAgentMode] = useState<"v2" | "v3" | "v4-deep">("v3");

  // Deep agent accordion state (active when agentMode === "v4-deep")
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
      agentMode === "v4-deep" && deepState.status !== "pending"
        ? <DeepAgentAccordion state={deepState} dispatch={deepDispatch} />
        : undefined,
    [agentMode, deepState, deepDispatch],
  );

  // Pagination state for loading older messages
  const [hasMoreMessages, setHasMoreMessages] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  // Memoize selectedDateRange object to prevent recreation on every render
  const selectedDateRange = useMemo(
    () => ({ start: dateRangeStart, end: dateRangeEnd }),
    [dateRangeStart, dateRangeEnd],
  );

  // Stable setter for date range
  const setSelectedDateRange = useCallback(
    (range: { start: string; end: string }) => {
      setDateRangeStart(range.start);
      setDateRangeEnd(range.end);
    },
    [],
  );

  const { messages, setMessages, chatId, setChatId } = useChatManager();

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
        msg.analysis_data.timeframe === selectedInterval
      ) {
        fibMessage = msg;
        break;
      }
    }

    // Type guard to ensure proper typing
    if (!fibMessage?.analysis_data) return null;
    return fibMessage.analysis_data as unknown as FibonacciMetadata;
  }, [messages, currentSymbol, selectedInterval]);

  // Chat mutation for user messages
  const chatMutation = useAnalysis(
    currentSymbol,
    selectedDateRange,
    setMessages,
    setSelectedDateRange,
    selectedInterval,
    chatId,
    setChatId,
    modelSettings,
    agentMode, // Pass agent mode (v2/v3/v4-deep)
    agentMode === "v4-deep" ? handleDeepEvent : undefined,
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
  );

  const priceDataQuery = useQuery({
    queryKey: [
      "priceData",
      currentSymbol,
      selectedInterval,
      selectedDateRange.start,
      selectedDateRange.end,
    ],
    queryFn: () => {
      // Don't send dates - just use period for all intervals
      // This follows the principle: "show what we got" - full data without filtering
      // 1m, 60m: compact mode (100 bars)
      // 1d, 1w, 1mo: full mode (20+ years)
      return marketService.getPriceData(currentSymbol, {
        interval: selectedInterval,
        period: getPeriodForInterval(selectedInterval),
        // No custom dates - always show full available data
      });
    },
    enabled: !!currentSymbol,
    staleTime: 30000,
    refetchInterval: 60000,
    retry: false,
  });

  const handleSymbolSelect = useCallback(async (symbol: string, name: string) => {
    setCurrentSymbol(symbol);
    setCurrentCompanyName(name);

    // Calculate date range for current interval
    const dateRange = calculateDateRange({ start: "", end: "" }, selectedInterval);
    setDateRangeStart(dateRange.start);
    setDateRangeEnd(dateRange.end);

    // Auto-create chat if this is a new chat (no chatId yet)
    if (!chatId) {
      try {
        const { chatService } = await import("../services/api");
        const result = await chatService.createChat();
        setChatId(result.chat_id);
        console.log("✅ Chat auto-created on symbol selection:", result.chat_id);
      } catch (error) {
        console.error("❌ Failed to auto-create chat:", error);
      }
    }
  }, [selectedInterval, chatId, setChatId]);

  const handleIntervalChange = useCallback((interval: TimeInterval) => {
    setSelectedInterval(interval);

    // Calculate appropriate date range for this interval
    const dateRange = calculateDateRange({ start: "", end: "" }, interval);
    setDateRangeStart(dateRange.start);
    setDateRangeEnd(dateRange.end);
  }, []);

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

    // Symbol is now passed directly in chat request (current_symbol field)
    // No need to flush UI state - eliminates race condition
    chatMutation.mutate(message); // All user messages go to LLM
    setMessage("");
  }, [message, chatMutation]);

  const isRestoringRef = useRef(false);

  const handleChatSelect = useCallback(
    async (chatId: string) => {
      // Prevent concurrent restoration requests
      if (isRestoringRef.current) {
        console.log("⏭️ Skipping chat select: restoration in progress");
        return;
      }

      isRestoringRef.current = true;
      try {
        await restoreChat(chatId);
        // After restoration, assume there might be more messages (will hide button if none)
        setHasMoreMessages(true);
      } finally {
        isRestoringRef.current = false;
      }
    },
    [restoreChat],
  );

  const handleNewChat = useCallback(() => {
    setMessages([]);
    setChatId(null);
    setCurrentSymbol("");
    setCurrentCompanyName("");
    setDateRangeStart("");
    setDateRangeEnd("");
    setHasMoreMessages(false); // Reset pagination
    deepDispatch({ type: 'RESET' }); // Reset deep accordion state
  }, [setMessages, setChatId, deepDispatch]);

  const handleLoadMore = useCallback(async () => {
    if (!chatId || isLoadingMore) return;

    setIsLoadingMore(true);
    try {
      // Import chatService dynamically
      const { chatService } = await import("../services/api");

      // Calculate offset (current message count)
      const currentOffset = messages.length;

      // Fetch next 50 messages
      const chatDetail = await chatService.getChatDetail(chatId, 50, currentOffset);

      if (chatDetail.messages.length === 0) {
        // No more messages to load
        setHasMoreMessages(false);
        return;
      }

      // Convert backend messages to frontend format
      const olderMessages = chatDetail.messages.map((msg) => ({
        role: msg.role as "user" | "assistant",
        content: msg.content,
        timestamp: msg.timestamp,
        analysis_data: msg.metadata?.raw_data as Record<string, unknown> | undefined,
        tool_call: msg.tool_call,
      }));

      // Prepend older messages to current messages
      setMessages((prev) => [...olderMessages, ...prev]);

      // Check if there might be even more messages
      setHasMoreMessages(chatDetail.messages.length === 50);
    } catch (error) {
      console.error("❌ Failed to load more messages:", error);
      setMessages((prev) => [
        {
          role: "assistant",
          content: "⚠️ Failed to load older messages. Please try again.",
          timestamp: new Date().toISOString(),
        },
        ...prev,
      ]);
    } finally {
      setIsLoadingMore(false);
    }
  }, [chatId, messages.length, isLoadingMore, setMessages]);

  return (
    <div className="bg-white overflow-hidden max-h-screen">
      {/* Desktop: CSS Grid with fixed sidebar + flexible chat + narrow chart */}
      {/* Mobile: Flex column with overlays */}
      <div className="mx-auto">
        <div className="relative">
          <div
            className="flex flex-col lg:grid lg:gap-0 h-[calc(100vh-5rem)]"
            style={{
              gridTemplateColumns: `${isSidebarCollapsed ? '48px' : '240px'} minmax(500px, 1fr) ${isChartCollapsed ? '48px' : 'minmax(500px, 800px)'}`,
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
                    onClick={() => setIsMobileSidebarVisible(!isMobileSidebarVisible)}
                    className="px-3 py-1.5 bg-white/90 backdrop-blur-sm border border-gray-200 rounded-lg shadow-sm text-xs font-medium text-gray-700 hover:bg-gray-50"
                  >
                    {isMobileSidebarVisible ? t('chat:mobile.hideSidebar') : t('chat:mobile.showChats')}
                  </button>
                  <button
                    onClick={() => setIsMobileChartVisible(true)}
                    className="ml-auto px-3 py-1.5 bg-white/90 backdrop-blur-sm border border-gray-200 rounded-lg shadow-sm text-xs font-medium text-gray-700 hover:bg-gray-50"
                  >
                    {t('chat:mobile.showChart')}
                  </button>
                </div>
              )}

              {/* Add padding-top to prevent toggle buttons from covering messages */}
              <div className="pt-12 lg:pt-0 flex flex-col h-full">
                <ChatMessages
                  messages={messages}
                  isAnalysisPending={
                    chatMutation.isPending || buttonMutation.isPending
                  }
                  chatId={chatId}
                  onLoadMore={handleLoadMore}
                  hasMore={hasMoreMessages}
                  isLoadingMore={isLoadingMore}
                  deepAccordion={deepAccordionElement}
                />

                {/* Agent Mode Toggle - Only enabled when starting new chat */}
                <div className="flex-shrink-0 px-4 py-2 border-t border-gray-100 bg-gray-50/50">
                  <div className="flex items-center gap-3 text-sm">
                    <span className="text-gray-600 font-medium">{t('chat:mode.label')}:</span>
                    <button
                      onClick={() => setAgentMode("v3")}
                      disabled={!!chatId}
                      className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
                        agentMode === "v3"
                          ? "bg-gradient-to-r from-blue-500 to-indigo-500 text-white shadow-md"
                          : "bg-white text-gray-700 hover:bg-gray-100"
                      } ${
                        chatId
                          ? "opacity-50 cursor-not-allowed"
                          : "cursor-pointer"
                      }`}
                      title={
                        chatId
                          ? t('chat:mode.locked')
                          : t('chat:mode.agentDescription')
                      }
                    >
                      🤖 {t('chat:mode.agent')}
                    </button>
                    <button
                      onClick={() => setAgentMode("v2")}
                      disabled={!!chatId}
                      className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
                        agentMode === "v2"
                          ? "bg-gradient-to-r from-purple-500 to-pink-500 text-white shadow-md"
                          : "bg-white text-gray-700 hover:bg-gray-100"
                      } ${
                        chatId
                          ? "opacity-50 cursor-not-allowed"
                          : "cursor-pointer"
                      }`}
                      title={
                        chatId
                          ? t('chat:mode.locked')
                          : t('chat:mode.copilotDescription')
                      }
                    >
                      👤 {t('chat:mode.copilot')}
                    </button>
                    <button
                      onClick={() => setAgentMode("v4-deep")}
                      disabled={!!chatId}
                      className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
                        agentMode === "v4-deep"
                          ? "bg-gradient-to-r from-amber-500 to-orange-500 text-white shadow-md"
                          : "bg-white text-gray-700 hover:bg-gray-100"
                      } ${
                        chatId
                          ? "opacity-50 cursor-not-allowed"
                          : "cursor-pointer"
                      }`}
                      title={
                        chatId
                          ? t('chat:mode.locked')
                          : t('chat:mode.deepDescription')
                      }
                    >
                      🔬 {t('chat:mode.deep')}
                    </button>
                    {chatId && (
                      <span className="ml-auto text-xs text-gray-500 italic">
                        {t('chat:mode.locked')}
                      </span>
                    )}
                  </div>
                </div>

                <ChatInput
                  message={message}
                  setMessage={setMessage}
                  onSendMessage={handleSendMessage}
                  isPending={chatMutation.isPending || buttonMutation.isPending}
                  currentSymbol={currentSymbol}
                  messages={messages}
                  modelSettings={modelSettings}
                  onModelSettingsChange={setModelSettings}
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
                    {t('chat:mobile.backToChat')}
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
