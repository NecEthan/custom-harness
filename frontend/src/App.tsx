import { useState, useRef } from 'react';
import './App.css';
import { useEventStream } from './hooks/useEventStream';
import { StatusIndicator } from './components/StatusIndicator';
import { MetricsPanel } from './components/MetricsPanel';
import { RunSummary } from './components/RunSummary';
import { ExecutionTimeline } from './components/ExecutionTimeline';

export default function App() {
  const [task, setTask] = useState('');
  const [runId, setRunId] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Each run gets a unique URL via ?_run=N — forces the hook to reset + reconnect
  const streamUrl = runId > 0 ? `/run/events?_run=${runId}` : null;
  const { events, metrics, status, isConnected, error } = useEventStream(streamUrl);

  const done = status === 'finished' || status === 'failed';
  const running = runId > 0 && !done;

  const handleRun = async () => {
    if (!task.trim() || isSubmitting) return;
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const res = await fetch('/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: task.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(body.detail ?? res.statusText);
      }
      setRunId(id => id + 1);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleNewRun = () => {
    setRunId(0);
    setTask('');
    setSubmitError(null);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleRun();
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-title">Agent Harness</div>
        <StatusIndicator status={status} isConnected={isConnected} />
      </header>

      <div className="task-bar">
        <textarea
          ref={inputRef}
          className="task-input"
          placeholder="Enter a task for the agent… (⌘↵ to run)"
          value={task}
          onChange={e => setTask(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          disabled={running}
        />
        <div className="task-actions">
          {!done && !running && (
            <button
              className="btn btn-primary"
              onClick={handleRun}
              disabled={isSubmitting || !task.trim()}
            >
              {isSubmitting ? 'Starting…' : 'Run Agent'}
            </button>
          )}
          {done && (
            <button className="btn btn-secondary" onClick={handleNewRun}>
              New Run
            </button>
          )}
        </div>
        {submitError && <div className="task-error">{submitError}</div>}
        {error && <div className="task-error">{error}</div>}
      </div>

      <div className="main-layout">
        <aside className="sidebar">
          <MetricsPanel metrics={metrics} />
          {done && (
            <RunSummary task={task} metrics={metrics} status={status} />
          )}
        </aside>
        <section className="timeline-container">
          <ExecutionTimeline events={events} />
        </section>
      </div>
    </div>
  );
}
