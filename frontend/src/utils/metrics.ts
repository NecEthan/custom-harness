/**
 * Pure metric calculation from event stream.
 * Exported as standalone functions so they are easy to unit test.
 */

import type { HarnessEvent } from '../types/events';

export interface PerTurnTokens {
  turn: number;
  inputTokens: number;
  outputTokens: number;
}

export interface Metrics {
  totalInputTokens: number;
  totalOutputTokens: number;
  totalTokens: number;
  modelCalls: number;
  toolCalls: number;
  totalModelLatency: number;
  totalTurns: number;
  startTime: number | null;
  endTime: number | null;
  /** Wall-clock duration in seconds, null until both start and end are known. */
  duration: number | null;
  /** Per-model-call token breakdown for the token growth chart. */
  perTurnTokens: PerTurnTokens[];
}

export const EMPTY_METRICS: Metrics = {
  totalInputTokens: 0,
  totalOutputTokens: 0,
  totalTokens: 0,
  modelCalls: 0,
  toolCalls: 0,
  totalModelLatency: 0,
  totalTurns: 0,
  startTime: null,
  endTime: null,
  duration: null,
  perTurnTokens: [],
};

export function calculateMetrics(events: HarnessEvent[]): Metrics {
  let totalInputTokens = 0;
  let totalOutputTokens = 0;
  let modelCalls = 0;
  let toolCalls = 0;
  let totalModelLatency = 0;
  let totalTurns = 0;
  let startTime: number | null = null;
  let endTime: number | null = null;
  const perTurnTokens: PerTurnTokens[] = [];

  for (const event of events) {
    switch (event.type) {
      case 'AgentStarted':
        startTime = event.timestamp;
        break;
      case 'ModelResponded':
        totalInputTokens += event.input_tokens;
        totalOutputTokens += event.output_tokens;
        totalModelLatency += event.latency;
        modelCalls++;
        perTurnTokens.push({
          turn: event.turn,
          inputTokens: event.input_tokens,
          outputTokens: event.output_tokens,
        });
        break;
      case 'ToolCalled':
        toolCalls++;
        break;
      case 'AgentFinished':
        totalTurns = event.total_turns;
        endTime = event.timestamp;
        break;
      case 'AgentFailed':
        endTime = event.timestamp;
        break;
    }
  }

  const duration =
    startTime !== null && endTime !== null ? endTime - startTime : null;

  return {
    totalInputTokens,
    totalOutputTokens,
    totalTokens: totalInputTokens + totalOutputTokens,
    modelCalls,
    toolCalls,
    totalModelLatency,
    totalTurns,
    startTime,
    endTime,
    duration,
    perTurnTokens,
  };
}

export function fmt(n: number): string {
  return n.toLocaleString();
}

export function fmtLatency(seconds: number): string {
  return `${seconds.toFixed(2)}s`;
}
