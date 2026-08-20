import { describe, it, expect } from 'vitest';
import { deriveStatus } from '../utils/status';
import type { HarnessEvent } from '../types/events';

function last(event: HarnessEvent): HarnessEvent[] {
  return [event];
}

describe('deriveStatus', () => {
  it('idle with no events', () => {
    expect(deriveStatus([])).toBe('idle');
  });

  it('starting after AgentStarted', () => {
    expect(deriveStatus(last({ type: 'AgentStarted', task: 't', timestamp: 1 }))).toBe('starting');
  });

  it('starting after TurnStarted', () => {
    expect(deriveStatus(last({ type: 'TurnStarted', turn: 1, timestamp: 1 }))).toBe('starting');
  });

  it('thinking after ModelCalled', () => {
    expect(
      deriveStatus(
        last({
          type: 'ModelCalled',
          turn: 1,
          model: 'm',
          message_count: 1,
          tool_count: 3,
          timestamp: 1,
        }),
      ),
    ).toBe('thinking');
  });

  it('running after ModelResponded', () => {
    expect(
      deriveStatus(
        last({
          type: 'ModelResponded',
          turn: 1,
          model: 'm',
          input_tokens: 100,
          output_tokens: 50,
          latency: 1,
          stop_reason: 'tool_use',
          timestamp: 2,
        }),
      ),
    ).toBe('running');
  });

  it('using-tool after ToolCalled', () => {
    expect(
      deriveStatus(
        last({
          type: 'ToolCalled',
          turn: 1,
          tool_use_id: 'tid',
          name: 'read_file',
          input: {},
          timestamp: 2,
        }),
      ),
    ).toBe('using-tool');
  });

  it('running after ToolResulted', () => {
    expect(
      deriveStatus(
        last({
          type: 'ToolResulted',
          turn: 1,
          tool_use_id: 'tid',
          name: 'read_file',
          output: 'content',
          is_error: false,
          duration: 0.05,
          timestamp: 2,
        }),
      ),
    ).toBe('running');
  });

  it('running after TurnEnded', () => {
    expect(
      deriveStatus(
        last({ type: 'TurnEnded', turn: 1, stop_reason: 'tool_use', text: '', timestamp: 3 }),
      ),
    ).toBe('running');
  });

  it('finished after AgentFinished', () => {
    expect(
      deriveStatus(
        last({ type: 'AgentFinished', total_turns: 2, final_text: 'done', timestamp: 5 }),
      ),
    ).toBe('finished');
  });

  it('failed after AgentFailed', () => {
    expect(
      deriveStatus(
        last({
          type: 'AgentFailed',
          turn: 1,
          error: 'timeout',
          error_type: 'TimeoutError',
          timestamp: 5,
        }),
      ),
    ).toBe('failed');
  });

  it('uses only the last event for status', () => {
    const events: HarnessEvent[] = [
      { type: 'AgentStarted', task: 't', timestamp: 1 },
      { type: 'TurnStarted', turn: 1, timestamp: 1.1 },
      { type: 'ModelCalled', turn: 1, model: 'm', message_count: 1, tool_count: 0, timestamp: 1.2 },
    ];
    expect(deriveStatus(events)).toBe('thinking');
  });

  it('failed status persists even with earlier events', () => {
    const events: HarnessEvent[] = [
      { type: 'AgentStarted', task: 't', timestamp: 1 },
      { type: 'AgentFailed', turn: 1, error: 'boom', error_type: 'Error', timestamp: 2 },
    ];
    expect(deriveStatus(events)).toBe('failed');
  });
});
