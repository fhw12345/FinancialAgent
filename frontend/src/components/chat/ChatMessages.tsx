/**
 * ChatMessages Component
 *
 * Renders the list of chat messages, including user messages,
 * assistant responses, and loading indicators.
 */

import React, { useEffect, useRef, useMemo } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { Loader2 } from "lucide-react";
import type { ChatMessage } from "../../types/api";
import { ToolMessageWrapper } from "./ToolMessageWrapper";
import { ToolExecutionProgress } from "./ToolExecutionProgress";

interface ChatMessagesProps {
  messages: ChatMessage[];
  isAnalysisPending: boolean;
  chatId: string | null;
  onLoadMore?: () => Promise<void>;
  hasMore?: boolean;
  isLoadingMore?: boolean;
  sortOrder?: "newest" | "oldest"; // Optional: sort messages by timestamp
  deepAccordion?: React.ReactNode; // Deep agent accordion tree (v4-deep mode)
}

const formatTimestamp = (timestamp: string) => {
  return new Date(timestamp).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
};

// Parse thinking content from message
const parseThinkingContent = (content: string): { thinking: string[]; mainContent: string } => {
  const thinkingRegex = /<thinking>(.*?)<\/thinking>/gs;
  const thinkingMatches: string[] = [];
  let match;

  while ((match = thinkingRegex.exec(content)) !== null) {
    thinkingMatches.push(match[1]);
  }

  // Remove thinking tags from main content
  const mainContent = content.replace(thinkingRegex, '').trim();

  return {
    thinking: thinkingMatches,
    mainContent: mainContent || content, // Fallback to original if empty
  };
};

// Memoized message component to prevent re-renders
const MessageBubble = React.memo<{ msg: ChatMessage; t: (key: string, options?: Record<string, unknown>) => string }>(({ msg, t }) => {
  // Memoize thinking content parsing to avoid re-parsing on every render
  const { thinking, mainContent } = useMemo(() => {
    return msg.role === "assistant"
      ? parseThinkingContent(msg.content)
      : { thinking: [], mainContent: msg.content };
  }, [msg.role, msg.content]);

  return (
    <div
      className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`px-4 py-3 rounded-lg ${
          msg.role === "user"
            ? "max-w-[85%] bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-sm"
            : "w-full bg-white text-gray-900 border border-gray-200 shadow-sm"
        }`}
      >
        {/* Thinking Content (Collapsible) */}
        {thinking.length > 0 && (
          <details className="mb-3 group">
            <summary className="cursor-pointer select-none px-3 py-2 flex items-center gap-2 bg-blue-50/60 hover:bg-blue-50 rounded-lg border border-blue-200/50 transition-colors">
              <svg className="w-4 h-4 text-blue-600 flex-shrink-0 group-open:rotate-90 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              <span className="text-xs font-medium text-blue-700">{t('chat:message.thinkingProcess')}</span>
              <span className="text-xs text-blue-600/70 ml-auto">{t('chat:message.thinkingChars', { count: thinking.join('').length })}</span>
            </summary>
            <div className="mt-2 p-3 bg-gray-50 rounded-lg border border-gray-200">
              <pre className="text-xs text-gray-600 whitespace-pre-wrap font-mono leading-relaxed overflow-x-auto">
{thinking.join('\n\n')}
              </pre>
            </div>
          </details>
        )}

        <div className="markdown-content text-sm max-w-none">
          {msg.role === "user" ? (
            <p className="text-sm">{msg.content}</p>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeRaw]}
              components={{
                h1: ({ children }) => (
                  <h1 className="text-xl font-bold mb-3 text-gray-900">
                    {children}
                  </h1>
                ),
                h2: ({ children }) => (
                  <h2 className="text-lg font-bold mb-3 text-gray-900">
                    {children}
                  </h2>
                ),
                h3: ({ children }) => (
                  <h3 className="text-base font-bold mb-2 text-gray-800">
                    {children}
                  </h3>
                ),
                p: ({ children }) => (
                  <p className="mb-3 last:mb-0 leading-relaxed text-sm">
                    {children}
                  </p>
                ),
                ul: ({ children }) => (
                  <ul className="list-disc list-inside mb-3 space-y-2 ml-2">
                    {children}
                  </ul>
                ),
                ol: ({ children }) => (
                  <ol className="list-decimal list-inside mb-3 space-y-2 ml-2">
                    {children}
                  </ol>
                ),
                li: ({ children }) => (
                  <li className="text-sm leading-relaxed">{children}</li>
                ),
                strong: ({ children }) => (
                  <strong className="font-semibold text-gray-900">
                    {children}
                  </strong>
                ),
                code: ({ className, children, ...props }) => {
                  const isInline = !className;
                  return isInline ? (
                    <code
                      className="bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded text-sm font-mono"
                      {...props}
                    >
                      {children}
                    </code>
                  ) : (
                    <code
                      className={`block bg-gray-800 text-gray-100 p-3 rounded text-sm font-mono overflow-x-auto ${className}`}
                      {...props}
                    >
                      {children}
                    </code>
                  );
                },
                pre: ({ children }) => (
                  <pre className="mb-3 rounded overflow-hidden">{children}</pre>
                ),
                blockquote: ({ children }) => (
                  <blockquote className="border-l-4 border-blue-500 pl-4 my-3 italic text-gray-700">
                    {children}
                  </blockquote>
                ),
                table: ({ children, style }) => (
                  <div className="overflow-x-auto mb-3">
                    <table
                      style={style}
                      className="min-w-full border-collapse border border-gray-300"
                    >
                      {children}
                    </table>
                  </div>
                ),
                thead: ({ children, style }) => (
                  <thead style={style} className="bg-gray-100">
                    {children}
                  </thead>
                ),
                tbody: ({ children, style }) => (
                  <tbody style={style}>{children}</tbody>
                ),
                tr: ({ children, style }) => (
                  <tr style={style} className="border-b border-gray-300">
                    {children}
                  </tr>
                ),
                th: ({ children, style }) => (
                  <th
                    style={style}
                    className="px-4 py-2 text-left font-semibold text-gray-900 border-r border-gray-300 last:border-r-0"
                  >
                    {children}
                  </th>
                ),
                td: ({ children, style }) => (
                  <td
                    style={style}
                    className="px-4 py-2 text-gray-800 border-r border-gray-300 last:border-r-0"
                  >
                    {children}
                  </td>
                ),
                // HTML elements for collapsible sections
                details: ({ children }) => (
                  <details className="my-3 border border-gray-300 rounded-lg p-3 bg-gray-50">
                    {children}
                  </details>
                ),
                summary: ({ children }) => (
                  <summary className="cursor-pointer font-medium text-blue-700 hover:text-blue-900 select-none">
                    {children}
                  </summary>
                ),
              }}
            >
              {mainContent}
            </ReactMarkdown>
          )}
        </div>
        <div className="text-xs opacity-70 mt-1">
          {formatTimestamp(msg.timestamp)}
        </div>
      </div>
    </div>
  );
});

MessageBubble.displayName = "MessageBubble";

export const ChatMessages: React.FC<ChatMessagesProps> = ({
  messages,
  isAnalysisPending,
  chatId,
  onLoadMore,
  hasMore = false,
  isLoadingMore = false,
  sortOrder = "oldest", // Default to oldest first (chronological) for chat messages
  deepAccordion,
}) => {
  const { t } = useTranslation(['chat', 'common']);
  const lastUserMessageRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const lastScrolledUserMessageRef = useRef<string | null>(null);
  const firstMessageIdRef = useRef<string | null>(null);

  // Scroll to last user message (or top if no user message) when chat loads
  useEffect(() => {
    // If no messages, reset tracking
    if (messages.length === 0) {
      lastScrolledUserMessageRef.current = null;
      firstMessageIdRef.current = null;
      return;
    }

    // Detect chat change by checking if first message ID changed
    const firstMessageId = String(messages[0]._id || messages[0].timestamp);
    const isChatChange = firstMessageIdRef.current !== null && firstMessageIdRef.current !== firstMessageId;

    if (isChatChange) {
      lastScrolledUserMessageRef.current = null;
    }
    firstMessageIdRef.current = firstMessageId;

    // Find the last user message - iterate backwards WITHOUT array copy
    let lastUserMessage: ChatMessage | null = null;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        lastUserMessage = messages[i];
        break;
      }
    }

    if (!lastUserMessage) {
      // No user messages - this is a legacy chat (only assistant messages)
      // Scroll to the top to show the beginning of the analysis
      if (lastScrolledUserMessageRef.current === null) {
        const SCROLL_DELAY_MS = 100;
        const timeoutId = setTimeout(() => {
          const messagesContainer = messagesEndRef.current?.closest('.overflow-y-auto');
          if (messagesContainer) {
            messagesContainer.scrollTop = 0;
          }
        }, SCROLL_DELAY_MS);
        lastScrolledUserMessageRef.current = 'no-user-messages';

        return () => clearTimeout(timeoutId);
      }
      return;
    }

    // Generate unique ID for this user message
    const userMessageId = String(
      lastUserMessage._id || lastUserMessage.timestamp,
    );

    // Check if this is a chat restoration (no previous scroll tracking)
    const isRestoringChat = lastScrolledUserMessageRef.current === null && messages.length > 1;

    if (isRestoringChat) {
      // On chat restoration: scroll to last USER message to see what was asked
      lastUserMessageRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      lastScrolledUserMessageRef.current = userMessageId;
    } else if (lastScrolledUserMessageRef.current !== userMessageId) {
      // On new user message: scroll to show that message at the start
      lastUserMessageRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      lastScrolledUserMessageRef.current = userMessageId;
    }
  }, [messages]);

  // Memoize filtered and sorted messages to avoid re-computing on every render
  const visibleMessages = useMemo(() => {
    const filtered = messages.filter(msg =>
      // Skip empty assistant messages (streaming placeholders)
      // BUT keep tool progress messages even if they have empty content
      msg.role !== "assistant" || msg.content.trim() || msg.tool_progress
    );

    // Sort messages based on sortOrder prop
    if (sortOrder === "newest") {
      // Newest first: reverse chronological order
      return [...filtered].sort((a, b) => {
        const timeA = new Date(a.timestamp).getTime();
        const timeB = new Date(b.timestamp).getTime();
        return timeB - timeA; // Descending (newest first)
      });
    }
    // Default: oldest first (chronological order) - no sorting needed as messages come in order
    return filtered;
  }, [messages, sortOrder]);

  // Compute last user message index against visibleMessages (used for accordion placement)
  const lastUserIdx = useMemo(() => {
    for (let i = visibleMessages.length - 1; i >= 0; i--) {
      if (visibleMessages[i].role === "user") {
        return i;
      }
    }
    return -1;
  }, [visibleMessages]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 min-h-0">
      {/* Chat ID Display - Debug info */}
      {chatId && (
        <div className="flex justify-center mb-2">
          <div className="px-3 py-1 text-xs font-mono text-gray-500 bg-gray-100 rounded-md border border-gray-200">
            {chatId}
          </div>
        </div>
      )}

      {/* Load More Button - Shows at top when chat has older messages */}
      {chatId && hasMore && onLoadMore && (
        <div className="flex justify-center mb-4">
          <button
            onClick={() => void onLoadMore()}
            disabled={isLoadingMore}
            className="px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg border border-blue-200 transition-colors flex items-center gap-2"
          >
            {isLoadingMore ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {t('common:buttons.loading')}
              </>
            ) : (
              t('chat:message.loadOlderMessages')
            )}
          </button>
        </div>
      )}

      {visibleMessages.map((msg: ChatMessage, index: number) => {
        const isLastUserMessage = msg.role === "user" && index === lastUserIdx;

        // Check if this is a tool progress message
        const isToolProgress = msg.role === "assistant" && msg.tool_progress;

        // Check if this is a tool message with tool_call metadata
        const isToolMessage = msg.role === "assistant" && msg.tool_call;

        return (
          <React.Fragment key={msg._id || msg.timestamp}>
            <div ref={isLastUserMessage ? lastUserMessageRef : null}>
              {isToolProgress && msg.tool_progress ? (
                <ToolExecutionProgress {...msg.tool_progress} />
              ) : isToolMessage && msg.tool_call ? (
                <ToolMessageWrapper
                  toolCall={msg.tool_call}
                  content={<MessageBubble msg={msg} t={t} />}
                />
              ) : (
                <MessageBubble msg={msg} t={t} />
              )}
            </div>
            {/* Deep accordion appears right after the last user message */}
            {isLastUserMessage && deepAccordion}
          </React.Fragment>
        );
      })}

      {/* Fallback: show accordion even if no user messages exist */}
      {lastUserIdx === -1 && deepAccordion}

      {/* Loading indicator (hidden when deep accordion is visible) */}
      {isAnalysisPending && !deepAccordion && (
        <div className="flex justify-start">
          <div className="w-full bg-white text-gray-900 px-4 py-3 rounded-lg border border-gray-200 shadow-sm">
            <div className="flex items-center gap-3">
              <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
              <span className="text-sm font-medium">{t('chat:message.analyzing')}</span>
            </div>
          </div>
        </div>
      )}

      {/* Invisible scroll target for bottom */}
      <div ref={messagesEndRef} />
    </div>
  );
};
