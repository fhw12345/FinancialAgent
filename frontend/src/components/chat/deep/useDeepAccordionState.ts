/**
 * useDeepAccordionState - Reducer hook for deep agent accordion tree.
 *
 * Manages the hierarchical state of sub-agents, tools, debate rounds,
 * and expand/collapse state. Driven by DeepStreamEvent actions from SSE.
 *
 * Phase-based tool routing: tools emitted during debate/rebuttal phases
 * are routed to the current debate round or rebuttal entry instead of
 * the subagent tools map.
 */

import { useReducer } from 'react';
import type {
  DeepAccordionState,
  DeepAccordionAction,
  SubAgentState,
  ToolState,
  DebateRoundState,
  RebuttalRound,
} from './types';

const INITIAL_STATE: DeepAccordionState = {
  symbol: '',
  status: 'pending',
  enableDebate: false,
  subagentOrder: [],
  subagents: {},
  currentPhase: null,
  debate: null,
  synthesisStarted: false,
  verdict: null,
  expanded: { main: true, subagents: {} },
};

/** Helper: create a new ToolState from TOOL_START action fields. */
function createTool(action: { toolName: string; displayName: string; inputs: Record<string, unknown> }): ToolState {
  return {
    name: action.toolName,
    displayName: action.displayName,
    status: 'running',
    durationMs: 0,
    outputPreview: '',
    inputs: action.inputs,
  };
}

/** Helper: update a ToolState from TOOL_END action fields. */
function completeTool(existing: ToolState | undefined, action: { toolName: string; status: 'success' | 'error'; durationMs: number; outputPreview: string }): ToolState {
  return {
    name: action.toolName,
    displayName: existing?.displayName ?? action.toolName,
    status: action.status === 'error' ? 'failed' : 'completed',
    durationMs: action.durationMs,
    outputPreview: action.outputPreview,
    inputs: existing?.inputs ?? {},
  };
}

/** Helper: immutably set a tool on the last item in an array's tools map. */
function setToolOnLastItem<T extends { tools: Record<string, ToolState> }>(
  items: T[],
  toolName: string,
  tool: ToolState,
): T[] {
  if (items.length === 0) return items;
  const copy = [...items];
  const last = copy[copy.length - 1];
  copy[copy.length - 1] = { ...last, tools: { ...last.tools, [toolName]: tool } };
  return copy;
}

/** Helper: get a tool from the last item in an array, or undefined. */
function getToolFromLastItem<T extends { tools: Record<string, ToolState> }>(
  items: T[],
  toolName: string,
): ToolState | undefined {
  if (items.length === 0) return undefined;
  return items[items.length - 1].tools[toolName];
}

function deepAccordionReducer(
  state: DeepAccordionState,
  action: DeepAccordionAction,
): DeepAccordionState {
  switch (action.type) {
    case 'DEEP_START': {
      const expandedSubagents: Record<string, boolean> = {};
      for (const name of action.subagentNames) {
        expandedSubagents[name] = true;
      }
      return {
        ...INITIAL_STATE,
        symbol: action.symbol,
        status: 'running',
        enableDebate: action.enableDebate,
        subagentOrder: action.subagentNames,
        currentPhase: 'research',
        expanded: { main: true, subagents: expandedSubagents },
      };
    }

    case 'SUBAGENT_START': {
      // During debate/rebuttal phases, debater/defender sub-agent events
      // should not create top-level subagent entries — tools are routed
      // to debate rounds/rebuttals instead.
      if (state.currentPhase === 'debate' || state.currentPhase === 'rebuttal') {
        return state;
      }
      // Idempotent: skip if already exists and running
      const existing = state.subagents[action.subagentName];
      if (existing && existing.status === 'running') {
        return state;
      }
      const sa: SubAgentState = {
        name: action.subagentName,
        displayName: action.displayName,
        icon: action.icon,
        status: 'running',
        toolNames: action.toolNames,
        tools: {},
        resultSummary: '',
        durationMs: 0,
        toolCount: 0,
      };
      return {
        ...state,
        subagents: { ...state.subagents, [action.subagentName]: sa },
      };
    }

    case 'TOOL_START': {
      const tool = createTool(action);

      // Phase-based routing: debate tools go to current debate round
      if (state.currentPhase === 'debate' && state.debate) {
        return { ...state, debate: { ...state.debate, rounds: setToolOnLastItem(state.debate.rounds, action.toolName, tool) } };
      }

      // Phase-based routing: rebuttal tools go to current rebuttal
      if (state.currentPhase === 'rebuttal' && state.debate) {
        return { ...state, debate: { ...state.debate, rebuttals: setToolOnLastItem(state.debate.rebuttals, action.toolName, tool) } };
      }

      // Research phase: route to subagent
      const sa = state.subagents[action.subagentName];
      if (!sa) return state;
      return {
        ...state,
        subagents: {
          ...state.subagents,
          [action.subagentName]: {
            ...sa,
            tools: { ...sa.tools, [action.toolName]: tool },
          },
        },
      };
    }

    case 'TOOL_END': {
      // Phase-based routing: debate tools
      if (state.currentPhase === 'debate' && state.debate) {
        const existing = getToolFromLastItem(state.debate.rounds, action.toolName);
        const tool = completeTool(existing, action);
        return { ...state, debate: { ...state.debate, rounds: setToolOnLastItem(state.debate.rounds, action.toolName, tool) } };
      }

      // Phase-based routing: rebuttal tools
      if (state.currentPhase === 'rebuttal' && state.debate) {
        const existing = getToolFromLastItem(state.debate.rebuttals, action.toolName);
        const tool = completeTool(existing, action);
        return { ...state, debate: { ...state.debate, rebuttals: setToolOnLastItem(state.debate.rebuttals, action.toolName, tool) } };
      }

      // Research phase: route to subagent
      const sa = state.subagents[action.subagentName];
      if (!sa) return state;
      const existingTool = sa.tools[action.toolName];
      const tool = completeTool(existingTool, action);
      return {
        ...state,
        subagents: {
          ...state.subagents,
          [action.subagentName]: {
            ...sa,
            tools: { ...sa.tools, [action.toolName]: tool },
          },
        },
      };
    }

    case 'SUBAGENT_RESULT': {
      // During debate/rebuttal, skip creating subagent result entries
      if (state.currentPhase === 'debate' || state.currentPhase === 'rebuttal') {
        return state;
      }
      const sa = state.subagents[action.subagentName];
      if (!sa) return state;

      return {
        ...state,
        subagents: {
          ...state.subagents,
          [action.subagentName]: {
            ...sa,
            status: action.status === 'error' ? 'failed' : 'completed',
            durationMs: action.durationMs,
            resultSummary: action.resultSummary,
            toolCount: action.toolCount,
          },
        },
      };
    }

    case 'DEBATE_START': {
      const pendingRound: DebateRoundState = {
        round: action.round,
        hasConcerns: false,
        summary: '',
        tools: {},
        durationMs: 0,
        status: 'running',
      };

      // Round 2+: preserve existing rounds/rebuttals (fix reset bug)
      if (state.debate) {
        return {
          ...state,
          currentPhase: 'debate',
          debate: {
            ...state.debate,
            status: 'running',
            currentRound: action.round,
            rounds: [...state.debate.rounds, pendingRound],
          },
        };
      }

      // First round
      return {
        ...state,
        currentPhase: 'debate',
        debate: {
          status: 'running',
          currentRound: action.round,
          maxRounds: action.maxRounds,
          rounds: [pendingRound],
          rebuttals: [],
        },
      };
    }

    case 'DEBATE_ROUND': {
      if (!state.debate) return state;
      // Update existing pending round (last entry) instead of appending
      const rounds = [...state.debate.rounds];
      const lastIdx = rounds.length - 1;
      if (lastIdx >= 0) {
        rounds[lastIdx] = {
          ...rounds[lastIdx],
          hasConcerns: action.hasConcerns,
          summary: action.summary,
          status: 'completed',
        };
      }
      return {
        ...state,
        debate: {
          ...state.debate,
          currentRound: action.round,
          status: action.hasConcerns ? 'running' : 'completed',
          rounds,
        },
      };
    }

    case 'REBUTTAL_START': {
      if (!state.debate) return state;
      const pendingRebuttal: RebuttalRound = {
        round: action.round,
        defenseSummary: '',
        toolCount: 0,
        durationMs: 0,
        tools: {},
        status: 'running',
      };
      return {
        ...state,
        currentPhase: 'rebuttal',
        debate: {
          ...state.debate,
          status: 'running',
          rebuttals: [...state.debate.rebuttals, pendingRebuttal],
        },
      };
    }

    case 'REBUTTAL_RESULT': {
      if (!state.debate) return state;
      // Update existing pending rebuttal (last entry) instead of appending
      const rebuttals = [...state.debate.rebuttals];
      const lastIdx = rebuttals.length - 1;
      if (lastIdx >= 0) {
        rebuttals[lastIdx] = {
          ...rebuttals[lastIdx],
          defenseSummary: action.defenseSummary,
          toolCount: action.toolCount,
          durationMs: action.durationMs,
          status: 'completed',
        };
      }
      return {
        ...state,
        debate: {
          ...state.debate,
          rebuttals,
        },
      };
    }

    case 'SYNTHESIS_START': {
      return { ...state, synthesisStarted: true };
    }

    case 'VERDICT': {
      return {
        ...state,
        status: 'completed',
        currentPhase: 'verdict',
        verdict: {
          verdictText: action.verdictText,
          riskLevel: action.riskLevel,
          toolCount: action.toolCount,
          totalDurationMs: action.totalDurationMs,
        },
        debate: state.debate
          ? { ...state.debate, status: 'completed' }
          : null,
      };
    }

    case 'TOGGLE_EXPAND': {
      if (action.level === 'main') {
        return {
          ...state,
          expanded: { ...state.expanded, main: !state.expanded.main },
        };
      }
      if (action.level === 'subagent' && action.key) {
        const subagents = { ...state.expanded.subagents };
        subagents[action.key] = !subagents[action.key];
        return {
          ...state,
          expanded: { ...state.expanded, subagents },
        };
      }
      return state;
    }

    case 'EXPAND_ALL': {
      const subagents: Record<string, boolean> = {};
      for (const name of state.subagentOrder) {
        subagents[name] = true;
      }
      return {
        ...state,
        expanded: { ...state.expanded, main: true, subagents },
      };
    }

    case 'COLLAPSE_ALL': {
      // Intentionally does NOT collapse the main section —
      // collapsing it would hide the toggle button itself.
      const subagents: Record<string, boolean> = {};
      for (const name of state.subagentOrder) {
        subagents[name] = false;
      }
      return {
        ...state,
        expanded: { ...state.expanded, subagents },
      };
    }

    case 'RESET':
      return INITIAL_STATE;

    default:
      return state;
  }
}

export function useDeepAccordionState() {
  const [state, dispatch] = useReducer(deepAccordionReducer, INITIAL_STATE);
  return { state, dispatch };
}

// Export reducer for testing
export { deepAccordionReducer, INITIAL_STATE };
