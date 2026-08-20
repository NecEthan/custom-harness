import type { HarnessEvent } from '../types/events';
import { EventCard } from './EventCard';

// ── group events into sections ────────────────────────────────────────────────

type SingleSection = { kind: 'single'; event: HarnessEvent };
type TurnSection = { kind: 'turn'; turn: number; events: HarnessEvent[] };
type Section = SingleSection | TurnSection;

function groupByTurn(events: HarnessEvent[]): Section[] {
  const sections: Section[] = [];
  let inTurn = false;
  let turnNum = 0;
  let turnEvents: HarnessEvent[] = [];

  for (const event of events) {
    if (event.type === 'AgentStarted') {
      sections.push({ kind: 'single', event });
    } else if (event.type === 'TurnStarted') {
      turnNum = event.turn;
      turnEvents = [event];
      inTurn = true;
    } else if (event.type === 'TurnEnded') {
      turnEvents.push(event);
      sections.push({ kind: 'turn', turn: turnNum, events: turnEvents });
      turnEvents = [];
      inTurn = false;
    } else if (event.type === 'AgentFinished' || event.type === 'AgentFailed') {
      if (inTurn && turnEvents.length > 0) {
        // In-progress turn — flush it
        sections.push({ kind: 'turn', turn: turnNum, events: turnEvents });
        turnEvents = [];
        inTurn = false;
      }
      sections.push({ kind: 'single', event });
    } else {
      if (inTurn) {
        turnEvents.push(event);
      } else {
        sections.push({ kind: 'single', event });
      }
    }
  }

  // Flush ongoing turn (still executing)
  if (inTurn && turnEvents.length > 0) {
    sections.push({ kind: 'turn', turn: turnNum, events: turnEvents });
  }

  return sections;
}

// ── TurnBlock ─────────────────────────────────────────────────────────────────

function TurnBlock({ section }: { section: TurnSection }) {
  return (
    <div className="turn-block" data-testid="turn-block">
      <div className="turn-header">Turn {section.turn}</div>
      <div className="turn-events">
        {section.events.map((ev, i) => (
          <EventCard key={i} event={ev} />
        ))}
      </div>
    </div>
  );
}

// ── public component ──────────────────────────────────────────────────────────

interface Props {
  events: HarnessEvent[];
}

export function ExecutionTimeline({ events }: Props) {
  if (events.length === 0) {
    return (
      <div className="timeline-empty">
        No events yet. Submit a task to start.
      </div>
    );
  }

  const sections = groupByTurn(events);

  return (
    <div className="timeline" data-testid="timeline">
      {sections.map((section, i) =>
        section.kind === 'turn' ? (
          <TurnBlock key={i} section={section} />
        ) : (
          <EventCard
            key={i}
            event={section.event}
            defaultOpen={
              section.event.type === 'AgentStarted' ||
              section.event.type === 'AgentFinished' ||
              section.event.type === 'AgentFailed'
            }
          />
        ),
      )}
    </div>
  );
}
