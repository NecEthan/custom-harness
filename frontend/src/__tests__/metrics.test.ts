import { describe, it, expect } from 'vitest';
import { calculateMetrics, EMPTY_METRICS } from '../utils/metrics';
import type { HarnessEvent } from '../types/events';

// ── helpers ──────────────────────────────────────────────────────────────────

function agentStarted(task = 'test'): HarnessEvent {
  return { type: 'AgentStarted', task, timestamp: 1.0 };
}

function modelResponded(turn: number, input: number, output: number, latency = 1.0): HarnessEvent {
  return {
    type: 'ModelResponded',
    turn,
    model: 'claude-sonnet-4-6',
    input_tokens: input,
    output_tokens: output,
    latency,
    stop_reason: 'end_turn',
    timestamp: turn + 1,
  };
}

function toolCalled(turn: number): HarnessEvent {
  return {
    type: 'ToolCalled',
    turn,
    tool_use_id: `tid-${turn}`,
    name: 'read_file',
    input: { path: 'src/main.py' },
    timestamp: turn + 0.5,
  };
}

function agentFinished(total_turns: number): HarnessEvent {
  return { type: 'AgentFinished', total_turns, final_text: 'done', timestamp: 10.0 };
}

function agentFailed(): HarnessEvent {
  return { type: 'AgentFailed', turn: 1, error: 'boom', error_type: 'RuntimeError', timestamp: 5.0 };
}

// ── tests ────────────────────────────────────────────────────────────────────

describe('calculateMetrics', () => {
  it('returns empty metrics for no events', () => {
    expect(calculateMetrics([])).toEqual(EMPTY_METRICS);
  });

  it('accumulates input tokens across turns', () => {
    const events: HarnessEvent[] = [
      agentStarted(),
      modelResponded(1, 100, 20),
      modelResponded(2, 250, 40),
      modelResponded(3, 500, 60),
      agentFinished(3),
    ];
    const m = calculateMetrics(events);
    expect(m.totalInputTokens).toBe(850);
  });

  it('accumulates output tokens across turns', () => {
    const events: HarnessEvent[] = [
      modelResponded(1, 100, 50),
      modelResponded(2, 200, 75),
      agentFinished(2),
    ];
    const m = calculateMetrics(events);
    expect(m.totalOutputTokens).toBe(125);
  });

  it('calculates total tokens as sum of input + output', () => {
    const events: HarnessEvent[] = [
      modelResponded(1, 1000, 200),
      modelResponded(2, 2000, 300),
    ];
    const m = calculateMetrics(events);
    expect(m.totalTokens).toBe(3500);
    expect(m.totalTokens).toBe(m.totalInputTokens + m.totalOutputTokens);
  });

  it('counts model calls correctly', () => {
    const events: HarnessEvent[] = [
      modelResponded(1, 100, 10),
      modelResponded(2, 200, 20),
      modelResponded(3, 300, 30),
    ];
    expect(calculateMetrics(events).modelCalls).toBe(3);
  });

  it('counts tool calls correctly', () => {
    const events: HarnessEvent[] = [
      toolCalled(1),
      toolCalled(1),
      toolCalled(2),
    ];
    expect(calculateMetrics(events).toolCalls).toBe(3);
  });

  it('accumulates model latency', () => {
    const events: HarnessEvent[] = [
      modelResponded(1, 100, 10, 1.5),
      modelResponded(2, 200, 20, 0.8),
    ];
    expect(calculateMetrics(events).totalModelLatency).toBeCloseTo(2.3);
  });

  it('captures total turns from AgentFinished', () => {
    const events: HarnessEvent[] = [agentFinished(4)];
    expect(calculateMetrics(events).totalTurns).toBe(4);
  });

  it('records startTime from AgentStarted', () => {
    const events: HarnessEvent[] = [
      { type: 'AgentStarted', task: 't', timestamp: 42.0 },
    ];
    expect(calculateMetrics(events).startTime).toBe(42.0);
  });

  it('records endTime from AgentFinished', () => {
    const events: HarnessEvent[] = [agentFinished(1)];
    expect(calculateMetrics(events).endTime).toBe(10.0);
  });

  it('records endTime from AgentFailed', () => {
    const events: HarnessEvent[] = [agentFailed()];
    expect(calculateMetrics(events).endTime).toBe(5.0);
  });

  it('calculates duration from start to finish timestamps', () => {
    const events: HarnessEvent[] = [
      { type: 'AgentStarted', task: 't', timestamp: 1.0 },
      agentFinished(2),
    ];
    const m = calculateMetrics(events);
    expect(m.duration).toBeCloseTo(9.0); // 10.0 - 1.0
  });

  it('duration is null if run not finished', () => {
    const events: HarnessEvent[] = [agentStarted()];
    expect(calculateMetrics(events).duration).toBeNull();
  });

  it('builds perTurnTokens breakdown', () => {
    const events: HarnessEvent[] = [
      modelResponded(1, 100, 50),
      modelResponded(2, 200, 80),
    ];
    const m = calculateMetrics(events);
    expect(m.perTurnTokens).toHaveLength(2);
    expect(m.perTurnTokens[0]).toEqual({ turn: 1, inputTokens: 100, outputTokens: 50 });
    expect(m.perTurnTokens[1]).toEqual({ turn: 2, inputTokens: 200, outputTokens: 80 });
  });

  it('input token growth is visible across turns', () => {
    // Typical pattern: input grows as tool results accumulate
    const events: HarnessEvent[] = [
      modelResponded(1, 2000, 100),
      modelResponded(2, 3500, 150),
      modelResponded(3, 5000, 200),
    ];
    const m = calculateMetrics(events);
    const inputs = m.perTurnTokens.map(t => t.inputTokens);
    // Each turn's input should be larger than the previous (token accumulation)
    expect(inputs[1]).toBeGreaterThan(inputs[0]);
    expect(inputs[2]).toBeGreaterThan(inputs[1]);
  });

  it('handles agent failed without turn', () => {
    const events: HarnessEvent[] = [
      agentStarted(),
      { type: 'AgentFailed', turn: null, error: 'startup error', error_type: 'ValueError', timestamp: 2.0 },
    ];
    const m = calculateMetrics(events);
    expect(m.endTime).toBe(2.0);
    expect(m.duration).toBeCloseTo(1.0);
  });

  it('zero tool calls when no ToolCalled events', () => {
    const events: HarnessEvent[] = [
      agentStarted(),
      modelResponded(1, 100, 50),
      agentFinished(1),
    ];
    expect(calculateMetrics(events).toolCalls).toBe(0);
  });
});
