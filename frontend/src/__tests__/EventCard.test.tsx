import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EventCard } from '../components/EventCard';
import type { HarnessEvent } from '../types/events';

function renderCard(event: HarnessEvent, defaultOpen = false) {
  return render(<EventCard event={event} defaultOpen={defaultOpen} />);
}

describe('EventCard', () => {
  describe('rendering event types', () => {
    it('renders AgentStarted', () => {
      renderCard({ type: 'AgentStarted', task: 'inspect codebase', timestamp: 1 });
      expect(screen.getByText('AgentStarted')).toBeInTheDocument();
    });

    it('renders ModelCalled with model in summary', () => {
      renderCard({
        type: 'ModelCalled',
        turn: 1,
        model: 'claude-sonnet-4-6',
        message_count: 3,
        tool_count: 4,
        timestamp: 1,
      });
      expect(screen.getByText('ModelCalled')).toBeInTheDocument();
      expect(screen.getByText(/claude-sonnet-4-6/)).toBeInTheDocument();
    });

    it('renders ModelResponded with latency in summary', () => {
      renderCard({
        type: 'ModelResponded',
        turn: 1,
        model: 'claude-sonnet-4-6',
        input_tokens: 3500,
        output_tokens: 150,
        latency: 1.23,
        stop_reason: 'end_turn',
        timestamp: 2,
      });
      expect(screen.getByText('ModelResponded')).toBeInTheDocument();
      expect(screen.getByText(/1\.23s/)).toBeInTheDocument();
    });

    it('renders ToolCalled with tool name in summary', () => {
      renderCard({
        type: 'ToolCalled',
        turn: 1,
        tool_use_id: 'tid-1',
        name: 'read_file',
        input: { path: 'src/auth.py' },
        timestamp: 2,
      });
      expect(screen.getByText('ToolCalled')).toBeInTheDocument();
      expect(screen.getAllByText('read_file').length).toBeGreaterThan(0);
    });

    it('renders ToolResulted success', () => {
      renderCard({
        type: 'ToolResulted',
        turn: 1,
        tool_use_id: 'tid-1',
        name: 'read_file',
        output: 'file contents',
        is_error: false,
        duration: 0.05,
        timestamp: 2,
      });
      expect(screen.getByText(/✓ ok/)).toBeInTheDocument();
    });

    it('renders ToolResulted error', () => {
      renderCard({
        type: 'ToolResulted',
        turn: 1,
        tool_use_id: 'tid-err',
        name: 'broken_tool',
        output: 'RuntimeError: exploded',
        is_error: true,
        duration: 0.01,
        timestamp: 2,
      });
      expect(screen.getByText(/✗ error/)).toBeInTheDocument();
    });

    it('renders AgentFinished', () => {
      renderCard({ type: 'AgentFinished', total_turns: 3, final_text: 'All done.', timestamp: 10 });
      expect(screen.getByText('AgentFinished')).toBeInTheDocument();
      expect(screen.getByText(/3 turns/)).toBeInTheDocument();
    });

    it('renders AgentFailed with error type in summary', () => {
      renderCard({
        type: 'AgentFailed',
        turn: 1,
        error: 'Connection refused',
        error_type: 'ConnectionError',
        timestamp: 5,
      });
      expect(screen.getByText('AgentFailed')).toBeInTheDocument();
      expect(screen.getByText(/ConnectionError/)).toBeInTheDocument();
    });
  });

  describe('expand / collapse', () => {
    it('is collapsed by default', () => {
      renderCard({ type: 'AgentStarted', task: 'test', timestamp: 1 });
      expect(screen.queryByText('Task')).not.toBeInTheDocument();
    });

    it('opens on click and shows details', () => {
      renderCard({ type: 'AgentStarted', task: 'inspect codebase', timestamp: 1 });
      fireEvent.click(screen.getByRole('button'));
      // 'Task' field key only appears when expanded
      expect(screen.getByText('Task')).toBeInTheDocument();
      // task text appears in both summary and body — verify at least one instance
      expect(screen.getAllByText('inspect codebase').length).toBeGreaterThanOrEqual(1);
    });

    it('closes when clicked again', () => {
      renderCard({ type: 'AgentStarted', task: 'test', timestamp: 1 });
      const btn = screen.getByRole('button');
      fireEvent.click(btn);
      expect(screen.getByText('Task')).toBeInTheDocument();
      fireEvent.click(btn);
      expect(screen.queryByText('Task')).not.toBeInTheDocument();
    });

    it('defaultOpen=true shows details immediately', () => {
      renderCard({ type: 'AgentFinished', total_turns: 2, final_text: 'done', timestamp: 5 }, true);
      expect(screen.getByText('Total turns')).toBeInTheDocument();
    });
  });

  describe('ModelResponded detail fields', () => {
    it('shows token counts in details', () => {
      renderCard(
        {
          type: 'ModelResponded',
          turn: 1,
          model: 'claude-sonnet-4-6',
          input_tokens: 3500,
          output_tokens: 150,
          latency: 1.23,
          stop_reason: 'end_turn',
          timestamp: 2,
        },
        true,
      );
      expect(screen.getByText('Input tokens')).toBeInTheDocument();
      expect(screen.getByText('3,500')).toBeInTheDocument();
      expect(screen.getByText('Output tokens')).toBeInTheDocument();
      expect(screen.getByText('150')).toBeInTheDocument();
    });
  });

  describe('tool failure rendering', () => {
    it('shows error output in ToolResulted details', () => {
      renderCard(
        {
          type: 'ToolResulted',
          turn: 1,
          tool_use_id: 'tid-err',
          name: 'write_file',
          output: 'PermissionError: access denied',
          is_error: true,
          duration: null,
          timestamp: 3,
        },
        true,
      );
      expect(screen.getByText(/PermissionError/)).toBeInTheDocument();
    });
  });

  describe('agent failure rendering', () => {
    it('shows error and error_type in AgentFailed details', () => {
      renderCard(
        {
          type: 'AgentFailed',
          turn: 2,
          error: 'API rate limit exceeded',
          error_type: 'RateLimitError',
          timestamp: 7,
        },
        true,
      );
      expect(screen.getByText('Error type')).toBeInTheDocument();
      // error_type appears in both summary and expanded body
      expect(screen.getAllByText('RateLimitError').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText(/API rate limit exceeded/)).toBeInTheDocument();
    });
  });
});
