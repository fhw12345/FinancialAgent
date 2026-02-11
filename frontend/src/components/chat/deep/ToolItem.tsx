/**
 * ToolItem - Individual tool execution row in the accordion tree.
 *
 * Shows tool status (spinner/check/X), display name, duration,
 * and optional input preview tooltip.
 */

import React from 'react';
import { Clock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { ToolState } from './types';
import { formatDuration, STATUS_ICONS, STATUS_COLORS } from './utils';

interface ToolItemProps {
  tool: ToolState;
}

function ToolItemInner({ tool }: ToolItemProps) {
  const { t } = useTranslation(['chat']);
  const Icon = STATUS_ICONS[tool.status] ?? Clock;
  const color = STATUS_COLORS[tool.status] ?? 'text-gray-400';
  const duration = formatDuration(tool.durationMs);
  const inputSymbol = tool.inputs?.symbol as string | undefined;

  return (
    <div
      className="flex items-center gap-2 px-3 py-1.5 text-sm group/tool"
      title={
        inputSymbol
          ? t('chat:deepAgent.toolInputHint', { symbol: inputSymbol })
          : undefined
      }
    >
      <span className="text-base flex-shrink-0">
        {'\u{1F527}'}
      </span>

      <Icon
        className={`w-3.5 h-3.5 flex-shrink-0 ${color} ${
          tool.status === 'running' ? 'animate-spin' : ''
        }`}
      />

      <span className="text-gray-700 dark:text-gray-300 truncate">
        {tool.displayName}
      </span>

      {inputSymbol && (
        <span className="px-1.5 py-0.5 text-[10px] font-mono bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 rounded flex-shrink-0">
          {inputSymbol}
        </span>
      )}

      {duration && (
        <span className="ml-auto text-xs text-gray-400 dark:text-gray-500 flex-shrink-0">
          {duration}
        </span>
      )}
    </div>
  );
}

export const ToolItem = React.memo(ToolItemInner);
