/**
 * TypeScript types mirroring harness/events.py — discriminated unions so
 * components can safely narrow to specific event fields.
 */

export type AgentStartedEvent = {
  type: 'AgentStarted';
  task: string;
  timestamp: number;
};

export type TurnStartedEvent = {
  type: 'TurnStarted';
  turn: number;
  timestamp: number;
};

export type ModelCalledEvent = {
  type: 'ModelCalled';
  turn: number;
  model: string;
  message_count: number;
  tool_count: number;
  messages: unknown[];       // full message list sent to LLM
  tools: unknown[];          // full tool schemas sent to LLM
  system: string;            // system prompt sent to LLM
  timestamp: number;
};

export type ModelRespondedEvent = {
  type: 'ModelResponded';
  turn: number;
  model: string;
  input_tokens: number;
  output_tokens: number;
  latency: number;
  stop_reason: string;
  content: unknown[];        // full normalized response content blocks
  timestamp: number;
};

export type ToolCalledEvent = {
  type: 'ToolCalled';
  turn: number;
  tool_use_id: string;
  name: string;
  input: Record<string, unknown>;
  timestamp: number;
};

export type ToolResultedEvent = {
  type: 'ToolResulted';
  turn: number;
  tool_use_id: string;
  name: string;
  output: string;
  is_error: boolean;
  duration: number | null;
  timestamp: number;
};

export type TurnEndedEvent = {
  type: 'TurnEnded';
  turn: number;
  stop_reason: string;
  text: string;
  timestamp: number;
};

export type AgentFinishedEvent = {
  type: 'AgentFinished';
  total_turns: number;
  final_text: string;
  timestamp: number;
};

export type AgentFailedEvent = {
  type: 'AgentFailed';
  turn: number | null;
  error: string;
  error_type: string;
  timestamp: number;
};

export type HarnessEvent =
  | AgentStartedEvent
  | TurnStartedEvent
  | ModelCalledEvent
  | ModelRespondedEvent
  | ToolCalledEvent
  | ToolResultedEvent
  | TurnEndedEvent
  | AgentFinishedEvent
  | AgentFailedEvent;
