/**
 * DebateSection - Debate verification phase in the accordion tree.
 *
 * Shows debate rounds with expandable claim/challenge/defense structure:
 * - Debater concerns with tool items (expandable)
 * - Defense with tool evidence and full text (expandable)
 */

import React, { useState } from 'react';
import {
  Loader2,
  CheckCircle2,
  AlertTriangle,
  ChevronRight,
  ChevronDown,
  Shield,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { DebateState, DebateRoundState, RebuttalRound } from './types';
import { ToolItem } from './ToolItem';
import { ExpandableText } from './ExpandableText';

interface DebateSectionProps {
  debate: DebateState;
}

function DebateRoundItem({
  round,
  rebuttal,
}: {
  round: DebateRoundState;
  rebuttal?: RebuttalRound;
}) {
  const { t } = useTranslation(['chat']);
  const [expanded, setExpanded] = useState(false);
  const debateTools = Object.values(round.tools);
  const rebuttalTools = rebuttal ? Object.values(rebuttal.tools) : [];

  return (
    <div className="border-t border-gray-200 dark:border-gray-700">
      {/* Round header (clickable) */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
      >
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
        )}

        {round.hasConcerns ? (
          <AlertTriangle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
        ) : (
          <CheckCircle2 className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
        )}

        <span className="text-xs font-medium text-gray-700 dark:text-gray-300 flex-1 text-left">
          {t('chat:deepAgent.roundLabel', { n: round.round })}
        </span>

        {round.status === 'running' && (
          <Loader2 className="w-3 h-3 text-amber-500 animate-spin flex-shrink-0" />
        )}

        {rebuttal && (
          <span className="text-xs text-gray-400">
            {(rebuttal.durationMs / 1000).toFixed(1)}s
          </span>
        )}
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="px-3 pb-2.5 space-y-2">
          {/* Debater tools */}
          {debateTools.length > 0 && (
            <div className="ml-5 py-1">
              {debateTools.map((tool) => (
                <ToolItem key={tool.name} tool={tool} />
              ))}
            </div>
          )}

          {/* Concerns raised (full text, expandable) */}
          {round.summary && (
            <div className="ml-5">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-xs">{'\u2696\uFE0F'}</span>
                <span className="text-xs font-medium text-amber-700 dark:text-amber-400">
                  {t('chat:deepAgent.concernsRaised', {
                    defaultValue: 'Concerns Raised',
                  })}
                </span>
              </div>
              <ExpandableText text={round.summary} maxLines={3} />
            </div>
          )}

          {/* Defense */}
          {rebuttal && (
            <div className="ml-5">
              <div className="flex items-center gap-1.5 mb-1">
                <Shield className="w-3 h-3 text-blue-500" />
                <span className="text-xs font-medium text-blue-700 dark:text-blue-400">
                  {t('chat:deepAgent.defense', {
                    defaultValue: 'Defense',
                  })}
                  {rebuttal.toolCount > 0 && (
                    <span className="font-normal text-gray-400 ml-1">
                      ({t('chat:deepAgent.toolsUsed', {
                        count: rebuttal.toolCount,
                      })})
                    </span>
                  )}
                </span>
              </div>

              {/* Rebuttal/defender tools */}
              {rebuttalTools.length > 0 && (
                <div className="py-1">
                  {rebuttalTools.map((tool) => (
                    <ToolItem key={tool.name} tool={tool} />
                  ))}
                </div>
              )}

              {/* Defense text (full, expandable) */}
              {rebuttal.defenseSummary && (
                <ExpandableText text={rebuttal.defenseSummary} maxLines={3} />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DebateSectionInner({ debate }: DebateSectionProps) {
  const { t } = useTranslation(['chat']);

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-amber-50/30 dark:bg-amber-900/10">
      {/* Header */}
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <span className="text-lg flex-shrink-0">{'\u2696\uFE0F'}</span>

        <span className="font-medium text-sm text-gray-900 dark:text-gray-100">
          {t('chat:deepAgent.debateVerification')}
        </span>

        {debate.status === 'running' && (
          <Loader2 className="w-4 h-4 text-amber-500 animate-spin flex-shrink-0" />
        )}
        {debate.status === 'completed' && (
          <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
        )}

        <span className="text-xs text-gray-500 dark:text-gray-400">
          {t('chat:deepAgent.debateRound', {
            current: debate.currentRound,
            max: debate.maxRounds,
          })}
        </span>
      </div>

      {/* Rounds with expandable claim/challenge/defense */}
      {debate.rounds.length > 0 &&
        debate.rounds.map((round) => {
          const rebuttal = debate.rebuttals?.find(
            (r) => r.round === round.round,
          );
          return (
            <DebateRoundItem
              key={round.round}
              round={round}
              rebuttal={rebuttal}
            />
          );
        })}
    </div>
  );
}

export const DebateSection = React.memo(DebateSectionInner);
