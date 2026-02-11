/**
 * VerdictSummaryCard - Compact summary card for completed deep analysis.
 *
 * Shows key metrics (tools used, duration, risk level) as a single row
 * with an expand/collapse all toggle for sub-agent sections.
 */

import React, { useCallback, useMemo } from 'react';
import { Wrench, Clock, ChevronsUpDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { VerdictState, DeepAccordionAction, ExpandedState } from './types';
import { formatDuration } from './utils';

interface VerdictSummaryCardProps {
  verdict: VerdictState;
  expanded: ExpandedState;
  dispatch: React.Dispatch<DeepAccordionAction>;
}

const RISK_STYLES: Record<string, string> = {
  HIGH: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  MODERATE: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  LOW: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
};

function VerdictSummaryCardInner({
  verdict,
  expanded,
  dispatch,
}: VerdictSummaryCardProps) {
  const { t } = useTranslation(['chat']);

  const allCollapsed = useMemo(() => {
    const values = Object.values(expanded.subagents);
    return values.length > 0 && values.every((v) => !v);
  }, [expanded.subagents]);

  const handleToggleAll = useCallback(() => {
    dispatch({ type: allCollapsed ? 'EXPAND_ALL' : 'COLLAPSE_ALL' });
  }, [dispatch, allCollapsed]);

  const duration = formatDuration(verdict.totalDurationMs);
  const riskStyle = verdict.riskLevel
    ? RISK_STYLES[verdict.riskLevel] ?? RISK_STYLES['MODERATE']
    : null;

  return (
    <div className="px-3 py-2 border-t border-gray-200 dark:border-gray-700">
      <div className="flex items-center flex-wrap gap-2 sm:gap-3 text-xs">
        {/* Tools used */}
        <span className="flex items-center gap-1 text-gray-500 dark:text-gray-400">
          <Wrench className="w-3 h-3" />
          {t('chat:deepAgent.toolsUsed', { count: verdict.toolCount })}
        </span>

        {/* Duration */}
        {duration && (
          <span className="flex items-center gap-1 text-gray-500 dark:text-gray-400">
            <Clock className="w-3 h-3" />
            {duration}
          </span>
        )}

        {/* Risk badge */}
        {verdict.riskLevel && riskStyle && (
          <span
            className={`px-1.5 py-0.5 rounded-full text-[10px] font-semibold ${riskStyle}`}
          >
            {t('chat:deepAgent.riskLevel', { level: verdict.riskLevel })}
          </span>
        )}

        {/* Expand/Collapse All toggle */}
        <button
          onClick={handleToggleAll}
          className="ml-auto flex items-center gap-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
          aria-label={allCollapsed ? t('chat:actions.expandAll') : t('chat:actions.collapseAll')}
        >
          <ChevronsUpDown className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}

export const VerdictSummaryCard = React.memo(VerdictSummaryCardInner);
