import { describe, it, expect } from 'vitest';
import { mapDeepEventToAction } from '../mapDeepEvent';
import type { DeepStreamEvent } from '../../../../types/api';

describe('mapDeepEventToAction', () => {
  it('maps deep_start → DEEP_START', () => {
    const event: DeepStreamEvent = {
      type: 'deep_start',
      seq: 1,
      timestamp: '2026-01-31T00:00:00Z',
      symbol: 'TSLA',
      subagent_names: ['tech', 'news', 'fin'],
      enable_debate: true,
    };

    expect(mapDeepEventToAction(event)).toEqual({
      type: 'DEEP_START',
      symbol: 'TSLA',
      subagentNames: ['tech', 'news', 'fin'],
      enableDebate: true,
    });
  });

  it('maps deep_subagent_start → SUBAGENT_START', () => {
    const event: DeepStreamEvent = {
      type: 'deep_subagent_start',
      seq: 2,
      timestamp: '2026-01-31T00:00:01Z',
      subagent_name: 'technical_analyst',
      display_name: 'Technical Analyst',
      icon: '📊',
      tool_names: ['fib', 'stoch'],
    };

    expect(mapDeepEventToAction(event)).toEqual({
      type: 'SUBAGENT_START',
      subagentName: 'technical_analyst',
      displayName: 'Technical Analyst',
      icon: '📊',
      toolNames: ['fib', 'stoch'],
    });
  });

  it('maps deep_tool_start → TOOL_START', () => {
    const event: DeepStreamEvent = {
      type: 'deep_tool_start',
      seq: 3,
      timestamp: '2026-01-31T00:00:02Z',
      subagent_name: 'tech',
      tool_name: 'fibonacci_analysis_tool',
      display_name: 'Fibonacci Analysis',
      inputs: { symbol: 'TSLA' },
    };

    expect(mapDeepEventToAction(event)).toEqual({
      type: 'TOOL_START',
      subagentName: 'tech',
      toolName: 'fibonacci_analysis_tool',
      displayName: 'Fibonacci Analysis',
      inputs: { symbol: 'TSLA' },
    });
  });

  it('maps deep_tool_end → TOOL_END (success)', () => {
    const event: DeepStreamEvent = {
      type: 'deep_tool_end',
      seq: 4,
      timestamp: '2026-01-31T00:00:03Z',
      subagent_name: 'tech',
      tool_name: 'fib',
      status: 'success',
      duration_ms: 1234,
      output_preview: 'Fibonacci levels calculated',
    };

    expect(mapDeepEventToAction(event)).toEqual({
      type: 'TOOL_END',
      subagentName: 'tech',
      toolName: 'fib',
      status: 'success',
      durationMs: 1234,
      outputPreview: 'Fibonacci levels calculated',
    });
  });

  it('maps deep_tool_end → TOOL_END (error)', () => {
    const event: DeepStreamEvent = {
      type: 'deep_tool_end',
      seq: 5,
      timestamp: '2026-01-31T00:00:04Z',
      subagent_name: 'tech',
      tool_name: 'fib',
      status: 'error',
      duration_ms: 500,
      output_preview: 'API timeout',
    };

    const action = mapDeepEventToAction(event);
    expect(action).toBeDefined();
    expect(action!.type).toBe('TOOL_END');
    if (action!.type === 'TOOL_END') {
      expect(action.status).toBe('error');
    }
  });

  it('maps deep_subagent_result → SUBAGENT_RESULT', () => {
    const event: DeepStreamEvent = {
      type: 'deep_subagent_result',
      seq: 6,
      timestamp: '2026-01-31T00:00:05Z',
      subagent_name: 'tech',
      status: 'success',
      duration_ms: 5000,
      result_summary: 'TSLA shows bearish divergence',
      tool_count: 3,
    };

    expect(mapDeepEventToAction(event)).toEqual({
      type: 'SUBAGENT_RESULT',
      subagentName: 'tech',
      status: 'success',
      durationMs: 5000,
      resultSummary: 'TSLA shows bearish divergence',
      toolCount: 3,
    });
  });

  it('maps deep_debate_start → DEBATE_START', () => {
    const event: DeepStreamEvent = {
      type: 'deep_debate_start',
      seq: 7,
      timestamp: '2026-01-31T00:00:06Z',
      round: 1,
      max_rounds: 3,
    };

    expect(mapDeepEventToAction(event)).toEqual({
      type: 'DEBATE_START',
      round: 1,
      maxRounds: 3,
    });
  });

  it('maps deep_debate_round → DEBATE_ROUND', () => {
    const event: DeepStreamEvent = {
      type: 'deep_debate_round',
      seq: 8,
      timestamp: '2026-01-31T00:00:07Z',
      round: 1,
      has_concerns: true,
      summary: 'Credit rating claim not verified',
    };

    expect(mapDeepEventToAction(event)).toEqual({
      type: 'DEBATE_ROUND',
      round: 1,
      hasConcerns: true,
      summary: 'Credit rating claim not verified',
    });
  });

  it('maps deep_synthesis_start → SYNTHESIS_START', () => {
    const event: DeepStreamEvent = {
      type: 'deep_synthesis_start',
      seq: 9,
      timestamp: '2026-01-31T00:00:08Z',
    };

    expect(mapDeepEventToAction(event)).toEqual({
      type: 'SYNTHESIS_START',
    });
  });

  it('maps deep_verdict → VERDICT', () => {
    const event: DeepStreamEvent = {
      type: 'deep_verdict',
      seq: 10,
      timestamp: '2026-01-31T00:00:09Z',
      verdict_text: 'TSLA is overvalued',
      risk_level: 'HIGH',
      tool_count: 8,
      total_duration_ms: 180000,
    };

    expect(mapDeepEventToAction(event)).toEqual({
      type: 'VERDICT',
      verdictText: 'TSLA is overvalued',
      riskLevel: 'HIGH',
      toolCount: 8,
      totalDurationMs: 180000,
    });
  });

  it('maps deep_verdict with null risk_level', () => {
    const event: DeepStreamEvent = {
      type: 'deep_verdict',
      seq: 11,
      timestamp: '2026-01-31T00:00:10Z',
      verdict_text: 'Analysis complete',
      risk_level: null,
      tool_count: 5,
      total_duration_ms: 120000,
    };

    const action = mapDeepEventToAction(event);
    expect(action).toBeDefined();
    if (action!.type === 'VERDICT') {
      expect(action.riskLevel).toBeNull();
    }
  });

  it('returns null for unknown event type', () => {
    const event = {
      type: 'deep_unknown',
      seq: 99,
      timestamp: '2026-01-31T00:00:00Z',
    } as unknown as DeepStreamEvent;

    expect(mapDeepEventToAction(event)).toBeNull();
  });

  describe('malformed events', () => {
    it('returns null for deep_start missing symbol', () => {
      const event = {
        type: 'deep_start',
        seq: 1,
        timestamp: '2026-01-31T00:00:00Z',
        symbol: undefined,
        subagent_names: ['tech'],
        enable_debate: false,
      } as unknown as DeepStreamEvent;

      expect(mapDeepEventToAction(event)).toBeNull();
    });

    it('returns null for deep_start with non-array subagent_names', () => {
      const event = {
        type: 'deep_start',
        seq: 1,
        timestamp: '2026-01-31T00:00:00Z',
        symbol: 'TSLA',
        subagent_names: 'not-an-array',
        enable_debate: false,
      } as unknown as DeepStreamEvent;

      expect(mapDeepEventToAction(event)).toBeNull();
    });

    it('returns null for deep_subagent_start missing subagent_name', () => {
      const event = {
        type: 'deep_subagent_start',
        seq: 2,
        timestamp: '2026-01-31T00:00:00Z',
        subagent_name: '',
        display_name: 'Tech',
        icon: '📊',
        tool_names: [],
      } as unknown as DeepStreamEvent;

      expect(mapDeepEventToAction(event)).toBeNull();
    });

    it('returns null for deep_tool_start missing tool_name', () => {
      const event = {
        type: 'deep_tool_start',
        seq: 3,
        timestamp: '2026-01-31T00:00:00Z',
        subagent_name: 'tech',
        tool_name: '',
        display_name: 'Fibonacci',
        inputs: {},
      } as unknown as DeepStreamEvent;

      expect(mapDeepEventToAction(event)).toBeNull();
    });
  });
});
