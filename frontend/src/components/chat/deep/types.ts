/**
 * Deep Agent Accordion State Types
 *
 * Defines the state shape for the hierarchical accordion tree
 * that renders deep agent analysis progress.
 */

export type DeepStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface ToolState {
  name: string;
  displayName: string;
  status: DeepStatus;
  durationMs: number;
  outputPreview: string;
  inputs: Record<string, unknown>;
}

export interface SubAgentState {
  name: string;
  displayName: string;
  icon: string;
  status: DeepStatus;
  toolNames: string[];
  tools: Record<string, ToolState>;
  resultSummary: string;
  durationMs: number;
  toolCount: number;
}

export interface DebateRoundState {
  round: number;
  hasConcerns: boolean;
  summary: string;
  tools: Record<string, ToolState>;
  durationMs: number;
  status: DeepStatus;
}

export interface RebuttalRound {
  round: number;
  defenseSummary: string;
  toolCount: number;
  durationMs: number;
  tools: Record<string, ToolState>;
  status: DeepStatus;
}

export interface DebateState {
  status: DeepStatus;
  currentRound: number;
  maxRounds: number;
  rounds: DebateRoundState[];
  rebuttals: RebuttalRound[];
}

export interface VerdictState {
  verdictText: string;
  riskLevel: string | null;
  toolCount: number;
  totalDurationMs: number;
}

export interface ExpandedState {
  main: boolean;
  subagents: Record<string, boolean>;
}

export type DeepPhase = 'research' | 'debate' | 'rebuttal' | 'verdict' | null;

export interface DeepAccordionState {
  symbol: string;
  status: DeepStatus;
  enableDebate: boolean;
  subagentOrder: string[];
  subagents: Record<string, SubAgentState>;
  currentPhase: DeepPhase;
  debate: DebateState | null;
  synthesisStarted: boolean;
  verdict: VerdictState | null;
  expanded: ExpandedState;
}

/** Actions dispatched by SSE event handlers */
export type DeepAccordionAction =
  | {
      type: 'DEEP_START';
      symbol: string;
      subagentNames: string[];
      enableDebate: boolean;
    }
  | {
      type: 'SUBAGENT_START';
      subagentName: string;
      displayName: string;
      icon: string;
      toolNames: string[];
    }
  | {
      type: 'TOOL_START';
      subagentName: string;
      toolName: string;
      displayName: string;
      inputs: Record<string, unknown>;
    }
  | {
      type: 'TOOL_END';
      subagentName: string;
      toolName: string;
      status: 'success' | 'error';
      durationMs: number;
      outputPreview: string;
    }
  | {
      type: 'SUBAGENT_RESULT';
      subagentName: string;
      status: 'success' | 'error';
      durationMs: number;
      resultSummary: string;
      toolCount: number;
    }
  | {
      type: 'DEBATE_START';
      round: number;
      maxRounds: number;
    }
  | {
      type: 'DEBATE_ROUND';
      round: number;
      hasConcerns: boolean;
      summary: string;
    }
  | { type: 'REBUTTAL_START'; round: number }
  | {
      type: 'REBUTTAL_RESULT';
      round: number;
      defenseSummary: string;
      toolCount: number;
      durationMs: number;
    }
  | { type: 'SYNTHESIS_START' }
  | {
      type: 'VERDICT';
      verdictText: string;
      riskLevel: string | null;
      toolCount: number;
      totalDurationMs: number;
    }
  | {
      type: 'TOGGLE_EXPAND';
      level: 'main' | 'subagent';
      key?: string;
    }
  | { type: 'EXPAND_ALL' }
  | { type: 'COLLAPSE_ALL' }
  | { type: 'RESET' };
