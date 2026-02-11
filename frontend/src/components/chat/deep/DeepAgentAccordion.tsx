/**
 * DeepAgentAccordion - Top-level container for deep agent analysis tree.
 *
 * Renders hierarchical accordion: Main Agent -> Sub-agents -> Tools.
 * Accepts a DeepAccordionState and dispatch function as props.
 * Pure rendering component - no SSE awareness.
 */

import React, { useCallback } from 'react';
import {
  ChevronRight,
  Loader2,
  CheckCircle2,
  XCircle,
  Sparkles,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { DeepAccordionState, DeepAccordionAction } from './types';
import { SubAgentSection } from './SubAgentSection';
import { DebateSection } from './DebateSection';
import { VerdictSummaryCard } from './VerdictSummaryCard';
import { formatDuration } from './utils';

interface DeepAgentAccordionProps {
  state: DeepAccordionState;
  dispatch: React.Dispatch<DeepAccordionAction>;
}

function DeepAgentAccordionInner({ state, dispatch }: DeepAgentAccordionProps) {
  const { t } = useTranslation(['chat']);

  const toggleMain = useCallback(() => {
    dispatch({ type: 'TOGGLE_EXPAND', level: 'main' });
  }, [dispatch]);

  const toggleSubagent = useCallback(
    (key: string) => {
      dispatch({ type: 'TOGGLE_EXPAND', level: 'subagent', key });
    },
    [dispatch],
  );

  // Don't render if no analysis started
  if (state.status === 'pending' && !state.symbol) {
    return null;
  }

  const statusIcon =
    state.status === 'running' ? (
      <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
    ) : state.status === 'completed' ? (
      <CheckCircle2 className="w-4 h-4 text-green-500" />
    ) : state.status === 'failed' ? (
      <XCircle className="w-4 h-4 text-red-500" />
    ) : null;

  const totalDuration = state.verdict
    ? formatDuration(state.verdict.totalDurationMs)
    : '';

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm mb-3 overflow-hidden">
      {/* Main header */}
      <button
        onClick={toggleMain}
        className="w-full flex items-center gap-2 sm:gap-3 px-3 sm:px-4 py-3 bg-gradient-to-r from-purple-50 to-blue-50 dark:from-purple-900/20 dark:to-blue-900/20 hover:from-purple-100 hover:to-blue-100 dark:hover:from-purple-900/30 dark:hover:to-blue-900/30 transition-colors"
        aria-expanded={state.expanded.main}
        aria-label={t('chat:deepAgent.toggleAnalysis')}
      >
        <ChevronRight
          className={`w-4 h-4 text-gray-500 flex-shrink-0 transition-transform duration-200 ${
            state.expanded.main ? 'rotate-90' : ''
          }`}
        />

        <Sparkles className="w-5 h-5 text-purple-500 flex-shrink-0" />

        <span className="font-semibold text-sm text-gray-900 dark:text-gray-100">
          {t('chat:deepAgent.deepAnalysis')}
        </span>

        {state.symbol && (
          <span className="px-2 py-0.5 text-xs font-mono font-bold bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded">
            {state.symbol}
          </span>
        )}

        {statusIcon}

        {totalDuration && (
          <span className="ml-auto text-xs text-gray-500 dark:text-gray-400">
            {totalDuration}
          </span>
        )}
      </button>

      {/* Expandable content */}
      <div
        className={`overflow-hidden transition-all duration-200 ${
          state.expanded.main ? 'max-h-[10000px] opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <div className="px-3 py-2 space-y-2">
          {/* Sub-agent sections */}
          {state.subagentOrder.map((name) => {
            const sa = state.subagents[name];
            if (!sa) return null;
            return (
              <SubAgentSection
                key={name}
                subagent={sa}
                subagentKey={name}
                isExpanded={state.expanded.subagents[name] ?? false}
                onToggle={toggleSubagent}
              />
            );
          })}

          {/* Synthesis indicator */}
          {state.synthesisStarted && !state.verdict && (
            <div className="flex items-center gap-2 px-3 py-2 text-sm text-gray-500 dark:text-gray-400">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>{t('chat:deepAgent.synthesizing')}</span>
            </div>
          )}

          {/* Debate section */}
          {state.debate && <DebateSection debate={state.debate} />}

          {/* Verdict summary card */}
          {state.verdict && (
            <VerdictSummaryCard
              verdict={state.verdict}
              expanded={state.expanded}
              dispatch={dispatch}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export const DeepAgentAccordion = React.memo(DeepAgentAccordionInner);
