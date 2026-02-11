/**
 * mapDeepEventToAction - Maps backend SSE DeepStreamEvent to reducer action.
 *
 * Pure function. Handles snake_case → camelCase field conversion.
 * Returns null for unknown/malformed events (caller should skip silently).
 */

import type { DeepStreamEvent } from '../../../types/api';
import type { DeepAccordionAction } from './types';

export function mapDeepEventToAction(
  event: DeepStreamEvent,
): DeepAccordionAction | null {
  switch (event.type) {
    case 'deep_start':
      if (!event.symbol || !Array.isArray(event.subagent_names)) return null;
      return {
        type: 'DEEP_START',
        symbol: event.symbol,
        subagentNames: event.subagent_names,
        enableDebate: event.enable_debate ?? false,
      };

    case 'deep_subagent_start':
      if (!event.subagent_name || !event.display_name) return null;
      return {
        type: 'SUBAGENT_START',
        subagentName: event.subagent_name,
        displayName: event.display_name,
        icon: event.icon ?? '',
        toolNames: event.tool_names ?? [],
      };

    case 'deep_tool_start':
      if (!event.subagent_name || !event.tool_name) return null;
      return {
        type: 'TOOL_START',
        subagentName: event.subagent_name,
        toolName: event.tool_name,
        displayName: event.display_name ?? event.tool_name,
        inputs: event.inputs ?? {},
      };

    case 'deep_tool_end':
      if (!event.subagent_name || !event.tool_name) return null;
      return {
        type: 'TOOL_END',
        subagentName: event.subagent_name,
        toolName: event.tool_name,
        status: event.status ?? 'success',
        durationMs: event.duration_ms ?? 0,
        outputPreview: event.output_preview ?? '',
      };

    case 'deep_subagent_result':
      if (!event.subagent_name) return null;
      return {
        type: 'SUBAGENT_RESULT',
        subagentName: event.subagent_name,
        status: event.status ?? 'success',
        durationMs: event.duration_ms ?? 0,
        resultSummary: event.result_summary ?? '',
        toolCount: event.tool_count ?? 0,
      };

    case 'deep_debate_start':
      return {
        type: 'DEBATE_START',
        round: event.round ?? 1,
        maxRounds: event.max_rounds ?? 3,
      };

    case 'deep_debate_round':
      return {
        type: 'DEBATE_ROUND',
        round: event.round ?? 1,
        hasConcerns: event.has_concerns ?? false,
        summary: event.summary ?? '',
      };

    case 'deep_rebuttal_start':
      return {
        type: 'REBUTTAL_START',
        round: event.round ?? 1,
      };

    case 'deep_rebuttal_result':
      return {
        type: 'REBUTTAL_RESULT',
        round: event.round ?? 1,
        defenseSummary: event.defense_summary ?? '',
        toolCount: event.tool_count ?? 0,
        durationMs: event.duration_ms ?? 0,
      };

    case 'deep_synthesis_start':
      return { type: 'SYNTHESIS_START' };

    case 'deep_verdict':
      return {
        type: 'VERDICT',
        verdictText: event.verdict_text ?? '',
        riskLevel: event.risk_level ?? null,
        toolCount: event.tool_count ?? 0,
        totalDurationMs: event.total_duration_ms ?? 0,
      };

    default:
      return null;
  }
}
