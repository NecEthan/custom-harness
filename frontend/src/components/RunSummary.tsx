import type { Metrics } from '../utils/metrics';
import { fmt, fmtLatency } from '../utils/metrics';
import type { RunStatus } from '../utils/status';
import { STATUS_COLOR } from '../utils/status';

interface Props {
  task: string;
  metrics: Metrics;
  status: RunStatus;
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="summary-row">
      <span className="summary-label">{label}</span>
      <span className="summary-value">{value}</span>
    </div>
  );
}

export function RunSummary({ task, metrics, status }: Props) {
  const succeeded = status === 'finished';
  const color = STATUS_COLOR[status];

  return (
    <div className="panel run-summary" data-testid="run-summary">
      <h2 className="panel-title">
        Run Summary{' '}
        <span style={{ color }}>{succeeded ? '✓' : '✗'}</span>
      </h2>

      <div className="summary-task">{task}</div>

      <div className="summary-group">
        <Row label="Status" value={succeeded ? 'Finished' : 'Failed'} />
        <Row label="Turns" value={metrics.totalTurns} />
        <Row label="Model calls" value={metrics.modelCalls} />
        <Row label="Tool calls" value={metrics.toolCalls} />
      </div>

      <div className="summary-group">
        <Row label="Input tokens" value={fmt(metrics.totalInputTokens)} />
        <Row label="Output tokens" value={fmt(metrics.totalOutputTokens)} />
        <Row label="Total tokens" value={fmt(metrics.totalTokens)} />
      </div>

      <div className="summary-group">
        <Row
          label="Model latency"
          value={metrics.modelCalls ? fmtLatency(metrics.totalModelLatency) : '—'}
        />
        <Row label="Duration" value={metrics.duration !== null ? fmtLatency(metrics.duration) : '—'} />
      </div>
    </div>
  );
}
