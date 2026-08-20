import { useState } from 'react';
import type { HarnessEvent } from '../types/events';
import { fmt, fmtLatency } from '../utils/metrics';

// ── colour classes ────────────────────────────────────────────────────────────

function eventClass(type: HarnessEvent['type']): string {
  switch (type) {
    case 'AgentStarted':
    case 'AgentFinished':
    case 'AgentFailed':
      return 'ev-agent';
    case 'ModelCalled':
    case 'ModelResponded':
      return 'ev-model';
    case 'ToolCalled':
    case 'ToolResulted':
      return 'ev-tool';
    case 'TurnStarted':
    case 'TurnEnded':
      return 'ev-turn';
    default:
      return '';
  }
}

// ── quick one-line summary beside the type name ───────────────────────────────

function quickSummary(event: HarnessEvent): string {
  switch (event.type) {
    case 'AgentStarted':
      return event.task.length > 60 ? event.task.slice(0, 57) + '…' : event.task;
    case 'ModelCalled':
      return `${event.model} · ${event.message_count} msg · ${event.tool_count} tools`;
    case 'ModelResponded':
      return `${fmtLatency(event.latency)} · ${event.stop_reason}`;
    case 'ToolCalled':
      return event.name;
    case 'ToolResulted':
      return event.is_error ? '✗ error' : `✓ ok${event.duration != null ? ` · ${fmtLatency(event.duration)}` : ''}`;
    case 'AgentFinished':
      return `${event.total_turns} turns`;
    case 'AgentFailed':
      return event.error_type;
    default:
      return '';
  }
}

// ── expanded detail body ──────────────────────────────────────────────────────

function Field({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="ev-field">
      <span className="ev-field-key">{k}</span>
      <span className="ev-field-val">{v}</span>
    </div>
  );
}

function ts(timestamp: number) {
  return new Date(timestamp * 1000).toLocaleTimeString();
}

function EventBody({ event }: { event: HarnessEvent }) {
  switch (event.type) {
    case 'AgentStarted':
      return (
        <>
          <Field k="Task" v={event.task} />
          <Field k="Time" v={ts(event.timestamp)} />
        </>
      );
    case 'TurnStarted':
      return (
        <>
          <Field k="Turn" v={event.turn} />
          <Field k="Time" v={ts(event.timestamp)} />
        </>
      );
    case 'ModelCalled':
      return (
        <>
          <Field k="Model" v={event.model} />
          <Field k="Messages" v={event.message_count} />
          <Field k="Tools" v={event.tool_count} />
          <Field k="Time" v={ts(event.timestamp)} />
        </>
      );
    case 'ModelResponded':
      return (
        <>
          <Field k="Model" v={event.model} />
          <Field k="Input tokens" v={fmt(event.input_tokens)} />
          <Field k="Output tokens" v={fmt(event.output_tokens)} />
          <Field k="Total tokens" v={fmt(event.input_tokens + event.output_tokens)} />
          <Field k="Latency" v={fmtLatency(event.latency)} />
          <Field k="Stop reason" v={event.stop_reason} />
          <Field k="Time" v={ts(event.timestamp)} />
        </>
      );
    case 'ToolCalled':
      return (
        <>
          <Field k="Tool" v={event.name} />
          <Field k="ID" v={<code>{event.tool_use_id}</code>} />
          <Field
            k="Input"
            v={
              <pre className="ev-pre">{JSON.stringify(event.input, null, 2)}</pre>
            }
          />
          <Field k="Time" v={ts(event.timestamp)} />
        </>
      );
    case 'ToolResulted': {
      const preview =
        event.output.length > 500
          ? event.output.slice(0, 497) + '…'
          : event.output;
      return (
        <>
          <Field k="Tool" v={event.name} />
          <Field k="Status" v={event.is_error ? '✗ error' : '✓ success'} />
          {event.duration != null && <Field k="Duration" v={fmtLatency(event.duration)} />}
          <Field k="ID" v={<code>{event.tool_use_id}</code>} />
          <Field k="Output" v={<pre className="ev-pre">{preview}</pre>} />
          <Field k="Time" v={ts(event.timestamp)} />
        </>
      );
    }
    case 'TurnEnded':
      return (
        <>
          <Field k="Turn" v={event.turn} />
          <Field k="Stop reason" v={event.stop_reason} />
          {event.text && (
            <Field
              k="Text"
              v={
                <pre className="ev-pre">
                  {event.text.length > 300 ? event.text.slice(0, 297) + '…' : event.text}
                </pre>
              }
            />
          )}
          <Field k="Time" v={ts(event.timestamp)} />
        </>
      );
    case 'AgentFinished':
      return (
        <>
          <Field k="Total turns" v={event.total_turns} />
          <Field
            k="Final text"
            v={
              <pre className="ev-pre">
                {event.final_text.length > 500
                  ? event.final_text.slice(0, 497) + '…'
                  : event.final_text}
              </pre>
            }
          />
          <Field k="Time" v={ts(event.timestamp)} />
        </>
      );
    case 'AgentFailed':
      return (
        <>
          {event.turn !== null && <Field k="Turn" v={event.turn} />}
          <Field k="Error type" v={event.error_type} />
          <Field k="Error" v={<pre className="ev-pre ev-error">{event.error}</pre>} />
          <Field k="Time" v={ts(event.timestamp)} />
        </>
      );
  }
}

// ── public component ──────────────────────────────────────────────────────────

interface Props {
  event: HarnessEvent;
  defaultOpen?: boolean;
}

export function EventCard({ event, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const cls = eventClass(event.type);
  const summary = quickSummary(event);

  return (
    <div className={`event-card ${cls}`} data-testid="event-card" data-type={event.type}>
      <button className="event-toggle" onClick={() => setOpen(o => !o)}>
        <span className="event-name">{event.type}</span>
        {summary && <span className="event-summary">{summary}</span>}
        <span className="event-chevron">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="event-body">
          <EventBody event={event} />
        </div>
      )}
    </div>
  );
}
