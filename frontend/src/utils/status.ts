/**
 * Derive current run status from the last event.
 * Pure function — easy to test and keeps status logic out of components.
 */

import type { HarnessEvent } from '../types/events';

export type RunStatus =
  | 'idle'
  | 'starting'
  | 'thinking'
  | 'using-tool'
  | 'running'
  | 'finished'
  | 'failed';

export function deriveStatus(events: HarnessEvent[]): RunStatus {
  if (events.length === 0) return 'idle';

  const last = events[events.length - 1];

  switch (last.type) {
    case 'AgentStarted':
      return 'starting';
    case 'TurnStarted':
      return 'starting';
    case 'ModelCalled':
      return 'thinking';
    case 'ModelResponded':
      return 'running';
    case 'ToolCalled':
      return 'using-tool';
    case 'ToolResulted':
      return 'running';
    case 'TurnEnded':
      return 'running';
    case 'AgentFinished':
      return 'finished';
    case 'AgentFailed':
      return 'failed';
    default:
      return 'running';
  }
}

export const STATUS_LABEL: Record<RunStatus, string> = {
  idle: 'Idle',
  starting: 'Starting',
  thinking: 'Thinking',
  'using-tool': 'Using tool',
  running: 'Running',
  finished: 'Finished',
  failed: 'Failed',
};

export const STATUS_COLOR: Record<RunStatus, string> = {
  idle: '#6b6b8a',
  starting: '#818cf8',
  thinking: '#22d3ee',
  'using-tool': '#fbbf24',
  running: '#818cf8',
  finished: '#4ade80',
  failed: '#f87171',
};
