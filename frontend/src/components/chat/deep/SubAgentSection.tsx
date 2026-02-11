/**
 * SubAgentSection - Sub-agent card with expandable tool list.
 *
 * Shows icon, display name, status badge, tool count, duration.
 * Expands to reveal individual tool items and result summary.
 */

import React, { useCallback } from 'react';
import { ChevronRight, Clock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { SubAgentState } from './types';
import { ToolItem } from './ToolItem';
import { ExpandableText } from './ExpandableText';
import { formatDuration, STATUS_ICONS, STATUS_COLORS, STATUS_BG } from './utils';

interface SubAgentSectionProps {
  subagent: SubAgentState;
  subagentKey: string;
  isExpanded: boolean;
  onToggle: (key: string) => void;
}

function SubAgentSectionInner({ subagent, subagentKey, isExpanded, onToggle }: SubAgentSectionProps) {
  const { t } = useTranslation(['chat']);
  const BadgeIcon = STATUS_ICONS[subagent.status] ?? Clock;
  const badgeColor = STATUS_COLORS[subagent.status] ?? 'text-gray-400';
  const badgeBg = STATUS_BG[subagent.status] ?? STATUS_BG.pending;
  const duration = formatDuration(subagent.durationMs);
  const tools = Object.values(subagent.tools);

  const handleToggle = useCallback(() => {
    onToggle(subagentKey);
  }, [onToggle, subagentKey]);

  return (
    <div className={`border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden ${badgeBg}`}>
      {/* Header */}
      <button
        onClick={handleToggle}
        className="w-full flex items-center gap-2.5 px-3 py-2.5 hover:bg-gray-100/50 dark:hover:bg-gray-800/50 transition-colors"
        aria-expanded={isExpanded}
        aria-label={
          isExpanded
            ? t('chat:deepAgent.collapseAgent', { name: subagent.displayName })
            : t('chat:deepAgent.expandAgent', { name: subagent.displayName })
        }
      >
        <ChevronRight
          className={`w-4 h-4 text-gray-400 flex-shrink-0 transition-transform duration-200 ${
            isExpanded ? 'rotate-90' : ''
          }`}
        />

        <span className="text-lg flex-shrink-0">{subagent.icon}</span>

        <span className="font-medium text-sm text-gray-900 dark:text-gray-100">
          {subagent.displayName}
        </span>

        <BadgeIcon
          className={`w-4 h-4 flex-shrink-0 ${badgeColor} ${
            subagent.status === 'running' ? 'animate-spin' : ''
          }`}
        />

        {subagent.toolCount > 0 && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {t('chat:deepAgent.toolsUsed', { count: subagent.toolCount })}
          </span>
        )}

        {duration && (
          <span className="ml-auto text-xs text-gray-400 dark:text-gray-500 flex-shrink-0">
            {duration}
          </span>
        )}
      </button>

      {/* Expandable content */}
      <div
        className={`overflow-hidden transition-all duration-200 ${
          isExpanded ? 'max-h-[2000px] opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <div className="border-t border-gray-200 dark:border-gray-700">
          {/* Tool list */}
          {tools.length > 0 && (
            <div className="py-1">
              {tools.map((tool) => (
                <ToolItem key={tool.name} tool={tool} />
              ))}
            </div>
          )}

          {/* Result summary (full text, expandable) */}
          {subagent.resultSummary && subagent.status === 'completed' && (
            <div className="px-3 py-2 border-t border-gray-200 dark:border-gray-700 bg-white/50 dark:bg-gray-900/50">
              <ExpandableText text={`\u{1F4DD} ${subagent.resultSummary}`} maxLines={3} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export const SubAgentSection = React.memo(SubAgentSectionInner);
