import { describe, it, expect } from 'vitest';
import { deepAccordionReducer, INITIAL_STATE } from '../useDeepAccordionState';
import type { DeepAccordionState, DeepAccordionAction } from '../types';

function applyActions(
  actions: DeepAccordionAction[],
  initialState: DeepAccordionState = INITIAL_STATE,
): DeepAccordionState {
  return actions.reduce(
    (state, action) => deepAccordionReducer(state, action),
    initialState,
  );
}

describe('deepAccordionReducer', () => {
  describe('DEEP_START', () => {
    it('initializes state with symbol and subagent names', () => {
      const state = deepAccordionReducer(INITIAL_STATE, {
        type: 'DEEP_START',
        symbol: 'TSLA',
        subagentNames: ['technical_analyst', 'news_analyst', 'financial_analyst'],
        enableDebate: true,
      });

      expect(state.symbol).toBe('TSLA');
      expect(state.status).toBe('running');
      expect(state.enableDebate).toBe(true);
      expect(state.subagentOrder).toEqual([
        'technical_analyst',
        'news_analyst',
        'financial_analyst',
      ]);
      expect(state.expanded.main).toBe(true);
      expect(state.expanded.subagents).toEqual({
        technical_analyst: true,
        news_analyst: true,
        financial_analyst: true,
      });
    });

    it('resets state on new DEEP_START', () => {
      const stateWithData = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'AAPL',
          subagentNames: ['a'],
          enableDebate: false,
        },
        {
          type: 'SUBAGENT_START',
          subagentName: 'a',
          displayName: 'Agent A',
          icon: '📊',
          toolNames: ['tool1'],
        },
      ]);

      const freshState = deepAccordionReducer(stateWithData, {
        type: 'DEEP_START',
        symbol: 'MSFT',
        subagentNames: ['b'],
        enableDebate: true,
      });

      expect(freshState.symbol).toBe('MSFT');
      expect(Object.keys(freshState.subagents)).toHaveLength(0);
    });
  });

  describe('SUBAGENT_START', () => {
    it('adds a new sub-agent in running state', () => {
      const state = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech'],
          enableDebate: false,
        },
        {
          type: 'SUBAGENT_START',
          subagentName: 'tech',
          displayName: 'Technical Analyst',
          icon: '📊',
          toolNames: ['fib', 'stoch'],
        },
      ]);

      const sa = state.subagents['tech'];
      expect(sa).toBeDefined();
      expect(sa.status).toBe('running');
      expect(sa.displayName).toBe('Technical Analyst');
      expect(sa.icon).toBe('📊');
      expect(sa.toolNames).toEqual(['fib', 'stoch']);
    });

    it('is idempotent for running sub-agents', () => {
      const baseState = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech'],
          enableDebate: false,
        },
        {
          type: 'SUBAGENT_START',
          subagentName: 'tech',
          displayName: 'Technical Analyst',
          icon: '📊',
          toolNames: ['fib'],
        },
      ]);

      const sameState = deepAccordionReducer(baseState, {
        type: 'SUBAGENT_START',
        subagentName: 'tech',
        displayName: 'Technical Analyst',
        icon: '📊',
        toolNames: ['fib'],
      });

      // Should return the exact same reference (idempotent)
      expect(sameState).toBe(baseState);
    });
  });

  describe('TOOL_START', () => {
    it('adds a tool in running state under its sub-agent', () => {
      const state = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech'],
          enableDebate: false,
        },
        {
          type: 'SUBAGENT_START',
          subagentName: 'tech',
          displayName: 'Technical',
          icon: '📊',
          toolNames: [],
        },
        {
          type: 'TOOL_START',
          subagentName: 'tech',
          toolName: 'fibonacci_analysis_tool',
          displayName: 'Fibonacci Analysis',
          inputs: { symbol: 'TSLA' },
        },
      ]);

      const tool = state.subagents['tech'].tools['fibonacci_analysis_tool'];
      expect(tool).toBeDefined();
      expect(tool.status).toBe('running');
      expect(tool.displayName).toBe('Fibonacci Analysis');
      expect(tool.inputs).toEqual({ symbol: 'TSLA' });
    });

    it('ignores tool for unknown sub-agent', () => {
      const state = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: [],
          enableDebate: false,
        },
        {
          type: 'TOOL_START',
          subagentName: 'nonexistent',
          toolName: 'tool1',
          displayName: 'Tool 1',
          inputs: {},
        },
      ]);

      expect(Object.keys(state.subagents)).toHaveLength(0);
    });
  });

  describe('TOOL_END', () => {
    it('marks tool as completed with duration', () => {
      const state = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech'],
          enableDebate: false,
        },
        {
          type: 'SUBAGENT_START',
          subagentName: 'tech',
          displayName: 'Tech',
          icon: '📊',
          toolNames: [],
        },
        {
          type: 'TOOL_START',
          subagentName: 'tech',
          toolName: 'fib',
          displayName: 'Fibonacci',
          inputs: { symbol: 'TSLA' },
        },
        {
          type: 'TOOL_END',
          subagentName: 'tech',
          toolName: 'fib',
          status: 'success',
          durationMs: 1234,
          outputPreview: 'Fibonacci levels calculated',
        },
      ]);

      const tool = state.subagents['tech'].tools['fib'];
      expect(tool.status).toBe('completed');
      expect(tool.durationMs).toBe(1234);
      expect(tool.outputPreview).toBe('Fibonacci levels calculated');
      // Should preserve inputs from TOOL_START
      expect(tool.inputs).toEqual({ symbol: 'TSLA' });
    });

    it('marks tool as failed on error status', () => {
      const state = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech'],
          enableDebate: false,
        },
        {
          type: 'SUBAGENT_START',
          subagentName: 'tech',
          displayName: 'Tech',
          icon: '📊',
          toolNames: [],
        },
        {
          type: 'TOOL_END',
          subagentName: 'tech',
          toolName: 'fib',
          status: 'error',
          durationMs: 500,
          outputPreview: 'API timeout',
        },
      ]);

      const tool = state.subagents['tech'].tools['fib'];
      expect(tool.status).toBe('failed');
    });
  });

  describe('SUBAGENT_RESULT', () => {
    it('marks sub-agent as completed with summary', () => {
      const state = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech'],
          enableDebate: false,
        },
        {
          type: 'SUBAGENT_START',
          subagentName: 'tech',
          displayName: 'Tech',
          icon: '📊',
          toolNames: [],
        },
        {
          type: 'SUBAGENT_RESULT',
          subagentName: 'tech',
          status: 'success',
          durationMs: 5000,
          resultSummary: 'TSLA shows bearish divergence',
          toolCount: 3,
        },
      ]);

      const sa = state.subagents['tech'];
      expect(sa.status).toBe('completed');
      expect(sa.durationMs).toBe(5000);
      expect(sa.resultSummary).toBe('TSLA shows bearish divergence');
      expect(sa.toolCount).toBe(3);
    });
  });

  describe('DEBATE_START', () => {
    it('initializes debate state with a pending round', () => {
      const state = deepAccordionReducer(INITIAL_STATE, {
        type: 'DEBATE_START',
        round: 1,
        maxRounds: 3,
      });

      expect(state.debate).toBeDefined();
      expect(state.debate!.status).toBe('running');
      expect(state.debate!.currentRound).toBe(1);
      expect(state.debate!.maxRounds).toBe(3);
      expect(state.debate!.rounds).toHaveLength(1);
      expect(state.debate!.rounds[0].status).toBe('running');
      expect(state.debate!.rounds[0].round).toBe(1);
      expect(state.currentPhase).toBe('debate');
    });

    it('preserves existing rounds on round 2 (no reset bug)', () => {
      const state = applyActions([
        { type: 'DEBATE_START', round: 1, maxRounds: 3 },
        {
          type: 'DEBATE_ROUND',
          round: 1,
          hasConcerns: true,
          summary: 'Round 1 concerns',
        },
        { type: 'REBUTTAL_START', round: 1 },
        {
          type: 'REBUTTAL_RESULT',
          round: 1,
          defenseSummary: 'Round 1 defense',
          toolCount: 2,
          durationMs: 5000,
        },
        // Round 2 should NOT reset round 1 data
        { type: 'DEBATE_START', round: 2, maxRounds: 3 },
      ]);

      expect(state.debate!.rounds).toHaveLength(2);
      expect(state.debate!.rounds[0].summary).toBe('Round 1 concerns');
      expect(state.debate!.rounds[0].status).toBe('completed');
      expect(state.debate!.rounds[1].status).toBe('running');
      expect(state.debate!.rounds[1].round).toBe(2);
      expect(state.debate!.rebuttals).toHaveLength(1);
    });
  });

  describe('DEBATE_ROUND', () => {
    it('updates pending round with concerns', () => {
      const state = applyActions([
        { type: 'DEBATE_START', round: 1, maxRounds: 3 },
        {
          type: 'DEBATE_ROUND',
          round: 1,
          hasConcerns: true,
          summary: 'Credit rating claim not verified',
        },
      ]);

      // DEBATE_START creates a pending round, DEBATE_ROUND updates it
      expect(state.debate!.rounds).toHaveLength(1);
      expect(state.debate!.rounds[0].hasConcerns).toBe(true);
      expect(state.debate!.rounds[0].summary).toBe('Credit rating claim not verified');
      expect(state.debate!.rounds[0].status).toBe('completed');
      expect(state.debate!.status).toBe('running');
    });

    it('marks debate completed when no concerns', () => {
      const state = applyActions([
        { type: 'DEBATE_START', round: 1, maxRounds: 3 },
        {
          type: 'DEBATE_ROUND',
          round: 1,
          hasConcerns: false,
          summary: 'No further concerns',
        },
      ]);

      expect(state.debate!.status).toBe('completed');
    });

    it('ignores debate round without debate state', () => {
      const state = deepAccordionReducer(INITIAL_STATE, {
        type: 'DEBATE_ROUND',
        round: 1,
        hasConcerns: false,
        summary: '',
      });

      expect(state.debate).toBeNull();
    });
  });

  describe('SYNTHESIS_START', () => {
    it('sets synthesisStarted to true', () => {
      const state = deepAccordionReducer(INITIAL_STATE, {
        type: 'SYNTHESIS_START',
      });
      expect(state.synthesisStarted).toBe(true);
    });
  });

  describe('VERDICT', () => {
    it('marks analysis as completed with verdict data', () => {
      const state = deepAccordionReducer(INITIAL_STATE, {
        type: 'VERDICT',
        verdictText: 'TSLA is overvalued',
        riskLevel: 'HIGH',
        toolCount: 8,
        totalDurationMs: 180000,
      });

      expect(state.status).toBe('completed');
      expect(state.verdict).toBeDefined();
      expect(state.verdict!.verdictText).toBe('TSLA is overvalued');
      expect(state.verdict!.riskLevel).toBe('HIGH');
      expect(state.verdict!.toolCount).toBe(8);
      expect(state.verdict!.totalDurationMs).toBe(180000);
    });

    it('allows null risk level', () => {
      const state = deepAccordionReducer(INITIAL_STATE, {
        type: 'VERDICT',
        verdictText: 'Analysis complete',
        riskLevel: null,
        toolCount: 5,
        totalDurationMs: 120000,
      });

      expect(state.verdict!.riskLevel).toBeNull();
    });
  });

  describe('TOGGLE_EXPAND', () => {
    it('toggles main expansion', () => {
      expect(INITIAL_STATE.expanded.main).toBe(true);

      const state1 = deepAccordionReducer(INITIAL_STATE, {
        type: 'TOGGLE_EXPAND',
        level: 'main',
      });
      expect(state1.expanded.main).toBe(false);

      const state2 = deepAccordionReducer(state1, {
        type: 'TOGGLE_EXPAND',
        level: 'main',
      });
      expect(state2.expanded.main).toBe(true);
    });

    it('toggles subagent expansion', () => {
      const base = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech'],
          enableDebate: false,
        },
      ]);
      expect(base.expanded.subagents['tech']).toBe(true);

      const collapsed = deepAccordionReducer(base, {
        type: 'TOGGLE_EXPAND',
        level: 'subagent',
        key: 'tech',
      });
      expect(collapsed.expanded.subagents['tech']).toBe(false);
    });

    it('ignores subagent toggle without key', () => {
      const state = deepAccordionReducer(INITIAL_STATE, {
        type: 'TOGGLE_EXPAND',
        level: 'subagent',
      });
      expect(state).toBe(INITIAL_STATE);
    });
  });

  describe('EXPAND_ALL', () => {
    it('expands all subagents and main', () => {
      const base = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech', 'news', 'fin'],
          enableDebate: false,
        },
      ]);
      // Collapse all first
      const collapsed = deepAccordionReducer(base, { type: 'COLLAPSE_ALL' });
      expect(collapsed.expanded.subagents['tech']).toBe(false);
      expect(collapsed.expanded.subagents['news']).toBe(false);
      expect(collapsed.expanded.subagents['fin']).toBe(false);

      // Expand all
      const expanded = deepAccordionReducer(collapsed, { type: 'EXPAND_ALL' });
      expect(expanded.expanded.main).toBe(true);
      expect(expanded.expanded.subagents['tech']).toBe(true);
      expect(expanded.expanded.subagents['news']).toBe(true);
      expect(expanded.expanded.subagents['fin']).toBe(true);
    });

    it('is idempotent when already expanded', () => {
      const base = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech'],
          enableDebate: false,
        },
      ]);
      expect(base.expanded.subagents['tech']).toBe(true);

      const expanded = deepAccordionReducer(base, { type: 'EXPAND_ALL' });
      expect(expanded.expanded.subagents['tech']).toBe(true);
    });
  });

  describe('COLLAPSE_ALL', () => {
    it('collapses all subagents', () => {
      const base = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech', 'news'],
          enableDebate: false,
        },
      ]);
      expect(base.expanded.subagents['tech']).toBe(true);
      expect(base.expanded.subagents['news']).toBe(true);

      const collapsed = deepAccordionReducer(base, { type: 'COLLAPSE_ALL' });
      expect(collapsed.expanded.subagents['tech']).toBe(false);
      expect(collapsed.expanded.subagents['news']).toBe(false);
    });

    it('does not collapse main section', () => {
      const base = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech'],
          enableDebate: false,
        },
      ]);

      const collapsed = deepAccordionReducer(base, { type: 'COLLAPSE_ALL' });
      // Main should remain as-is (true from DEEP_START)
      expect(collapsed.expanded.main).toBe(true);
      expect(collapsed.expanded.subagents['tech']).toBe(false);
    });

    it('handles empty subagent list', () => {
      const state = deepAccordionReducer(INITIAL_STATE, { type: 'COLLAPSE_ALL' });
      expect(state.expanded.subagents).toEqual({});
    });
  });

  describe('RESET', () => {
    it('resets state back to initial', () => {
      const stateWithData = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech'],
          enableDebate: true,
        },
        {
          type: 'SUBAGENT_START',
          subagentName: 'tech',
          displayName: 'Tech',
          icon: '📊',
          toolNames: ['fib'],
        },
      ]);
      expect(stateWithData.status).toBe('running');

      const resetState = deepAccordionReducer(stateWithData, { type: 'RESET' });
      expect(resetState).toEqual(INITIAL_STATE);
    });
  });

  describe('Phase-based tool routing', () => {
    it('routes tools to debate round during debate phase', () => {
      const state = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech'],
          enableDebate: true,
        },
        { type: 'DEBATE_START', round: 1, maxRounds: 3 },
        // Tool during debate phase should go to round's tools, not subagent
        {
          type: 'TOOL_START',
          subagentName: 'debater',
          toolName: 'get_news_sentiment',
          displayName: 'News Sentiment',
          inputs: { symbol: 'TSLA' },
        },
        {
          type: 'TOOL_END',
          subagentName: 'debater',
          toolName: 'get_news_sentiment',
          status: 'success',
          durationMs: 500,
          outputPreview: 'Bearish sentiment',
        },
      ]);

      // Tool should be in debate round, not in subagents
      expect(state.debate!.rounds[0].tools['get_news_sentiment']).toBeDefined();
      expect(state.debate!.rounds[0].tools['get_news_sentiment'].status).toBe('completed');
      expect(state.subagents['debater']).toBeUndefined();
    });

    it('routes tools to rebuttal during rebuttal phase', () => {
      const state = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech'],
          enableDebate: true,
        },
        { type: 'DEBATE_START', round: 1, maxRounds: 3 },
        {
          type: 'DEBATE_ROUND',
          round: 1,
          hasConcerns: true,
          summary: 'Concerns found',
        },
        { type: 'REBUTTAL_START', round: 1 },
        {
          type: 'TOOL_START',
          subagentName: 'financial_analyst',
          toolName: 'get_financial_statements',
          displayName: 'Financial Statements',
          inputs: { symbol: 'TSLA' },
        },
        {
          type: 'TOOL_END',
          subagentName: 'financial_analyst',
          toolName: 'get_financial_statements',
          status: 'success',
          durationMs: 1200,
          outputPreview: 'Cash flow data',
        },
      ]);

      // Tool should be in rebuttal, not in subagents
      expect(state.debate!.rebuttals[0].tools['get_financial_statements']).toBeDefined();
      expect(state.debate!.rebuttals[0].tools['get_financial_statements'].status).toBe('completed');
    });

    it('skips subagent start/result during debate phase', () => {
      const state = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech'],
          enableDebate: true,
        },
        { type: 'DEBATE_START', round: 1, maxRounds: 3 },
        // Debater subagent events should be skipped
        {
          type: 'SUBAGENT_START',
          subagentName: 'debater',
          displayName: 'Debater',
          icon: '⚖️',
          toolNames: ['tool1'],
        },
        {
          type: 'SUBAGENT_RESULT',
          subagentName: 'debater',
          status: 'success',
          durationMs: 5000,
          resultSummary: 'Critique done',
          toolCount: 2,
        },
      ]);

      // Debater should NOT appear in subagents map
      expect(state.subagents['debater']).toBeUndefined();
    });
  });

  describe('Full lifecycle', () => {
    it('processes complete analysis sequence', () => {
      const state = applyActions([
        {
          type: 'DEEP_START',
          symbol: 'TSLA',
          subagentNames: ['tech', 'news', 'fin'],
          enableDebate: true,
        },
        // Technical analyst
        {
          type: 'SUBAGENT_START',
          subagentName: 'tech',
          displayName: 'Technical',
          icon: '📊',
          toolNames: ['fib'],
        },
        {
          type: 'TOOL_START',
          subagentName: 'tech',
          toolName: 'fib',
          displayName: 'Fibonacci',
          inputs: { symbol: 'TSLA' },
        },
        {
          type: 'TOOL_END',
          subagentName: 'tech',
          toolName: 'fib',
          status: 'success',
          durationMs: 800,
          outputPreview: 'done',
        },
        {
          type: 'SUBAGENT_RESULT',
          subagentName: 'tech',
          status: 'success',
          durationMs: 2000,
          resultSummary: 'Bearish',
          toolCount: 1,
        },
        // Synthesis
        { type: 'SYNTHESIS_START' },
        // Debate
        { type: 'DEBATE_START', round: 1, maxRounds: 3 },
        {
          type: 'DEBATE_ROUND',
          round: 1,
          hasConcerns: false,
          summary: 'No concerns',
        },
        // Verdict
        {
          type: 'VERDICT',
          verdictText: 'TSLA overvalued',
          riskLevel: 'HIGH',
          toolCount: 1,
          totalDurationMs: 60000,
        },
      ]);

      expect(state.status).toBe('completed');
      expect(state.subagents['tech'].status).toBe('completed');
      expect(state.synthesisStarted).toBe(true);
      expect(state.debate!.status).toBe('completed');
      expect(state.verdict!.riskLevel).toBe('HIGH');
      expect(state.currentPhase).toBe('verdict');
    });
  });
});
