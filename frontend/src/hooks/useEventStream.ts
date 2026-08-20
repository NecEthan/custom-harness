/**
 * Subscribe to the harness SSE stream and accumulate events.
 * Returns events + derived metrics + status.
 */

import { useEffect, useState } from 'react';
import type { HarnessEvent } from '../types/events';
import { calculateMetrics, EMPTY_METRICS, type Metrics } from '../utils/metrics';
import { deriveStatus, type RunStatus } from '../utils/status';

export interface StreamState {
  events: HarnessEvent[];
  metrics: Metrics;
  status: RunStatus;
  isConnected: boolean;
  error: string | null;
}

const INITIAL: StreamState = {
  events: [],
  metrics: EMPTY_METRICS,
  status: 'idle',
  isConnected: false,
  error: null,
};

/**
 * @param url  SSE endpoint to connect to, or null to stay idle.
 *             Pass a new URL (include a unique query param) to reset and reconnect.
 */
export function useEventStream(url: string | null): StreamState {
  const [state, setState] = useState<StreamState>(INITIAL);

  useEffect(() => {
    // Reset on every URL change (including null → something)
    setState(INITIAL);
    if (!url) return;

    const source = new EventSource(url);
    setState(s => ({ ...s, isConnected: true }));

    source.onmessage = (e: MessageEvent<string>) => {
      const event = JSON.parse(e.data) as HarnessEvent;
      setState(prev => {
        const events = [...prev.events, event];
        return {
          events,
          metrics: calculateMetrics(events),
          status: deriveStatus(events),
          isConnected: prev.isConnected,
          error: null,
        };
      });

      if (event.type === 'AgentFinished' || event.type === 'AgentFailed') {
        source.close();
        setState(s => ({ ...s, isConnected: false }));
      }
    };

    source.onerror = () => {
      source.close();
      setState(s => ({ ...s, isConnected: false, error: 'Connection lost' }));
    };

    return () => {
      source.close();
    };
  }, [url]);

  return state;
}
