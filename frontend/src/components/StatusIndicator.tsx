import type { RunStatus } from '../utils/status';
import { STATUS_COLOR, STATUS_LABEL } from '../utils/status';

interface Props {
  status: RunStatus;
  isConnected: boolean;
}

export function StatusIndicator({ status, isConnected }: Props) {
  const color = STATUS_COLOR[status];
  const label = STATUS_LABEL[status];
  const pulse = status === 'thinking' || status === 'using-tool' || status === 'running' || status === 'starting';

  return (
    <div className="status-indicator">
      <span
        className={pulse ? 'status-dot pulse' : 'status-dot'}
        style={{ background: color, boxShadow: `0 0 6px ${color}` }}
      />
      <span className="status-label" style={{ color }}>
        {label}
      </span>
      {isConnected && (
        <span className="status-badge connected">● SSE</span>
      )}
    </div>
  );
}
