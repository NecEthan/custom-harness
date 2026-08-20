import type { Metrics, PerTurnTokens } from '../utils/metrics';
import { fmt, fmtLatency } from '../utils/metrics';

interface Props {
  metrics: Metrics;
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric-row">
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
    </div>
  );
}

function TurnTokensRow({ row }: { row: PerTurnTokens }) {
  return (
    <div className="turn-token-row">
      <span className="turn-token-label">Turn {row.turn}</span>
      <span className="turn-token-in">↑ {fmt(row.inputTokens)}</span>
      <span className="turn-token-out">↓ {fmt(row.outputTokens)}</span>
    </div>
  );
}

export function MetricsPanel({ metrics }: Props) {
  const {
    totalInputTokens,
    totalOutputTokens,
    totalTokens,
    modelCalls,
    toolCalls,
    totalModelLatency,
    totalTurns,
    duration,
    perTurnTokens,
  } = metrics;

  return (
    <div className="panel metrics-panel">
      <h2 className="panel-title">Metrics</h2>

      <div className="metric-group">
        <Row label="Turns" value={totalTurns || '—'} />
        <Row label="Model calls" value={modelCalls || '—'} />
        <Row label="Tool calls" value={toolCalls || '—'} />
      </div>

      <div className="metric-group">
        <Row label="Input tokens" value={totalInputTokens ? fmt(totalInputTokens) : '—'} />
        <Row label="Output tokens" value={totalOutputTokens ? fmt(totalOutputTokens) : '—'} />
        <Row label="Total tokens" value={totalTokens ? fmt(totalTokens) : '—'} />
      </div>

      <div className="metric-group">
        <Row label="Model latency" value={modelCalls ? fmtLatency(totalModelLatency) : '—'} />
        <Row label="Duration" value={duration !== null ? fmtLatency(duration) : '—'} />
      </div>

      {perTurnTokens.length > 0 && (
        <div className="metric-group">
          <div className="metric-subheader">Token growth per turn</div>
          {perTurnTokens.map((row, i) => (
            <TurnTokensRow key={i} row={row} />
          ))}
        </div>
      )}
    </div>
  );
}
