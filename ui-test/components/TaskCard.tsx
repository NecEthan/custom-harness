'use client';

import type { Task } from '@/types';

interface Props {
  task: Task;
  onEdit: () => void;
  onDelete: () => void;
  onStatusChange: (status: Task['status']) => void;
}

const STATUS_LABELS: Record<Task['status'], string> = {
  todo: 'Todo',
  in_progress: 'In Progress',
  done: 'Done',
};

const PRIORITY_LABELS: Record<Task['priority'], string> = {
  low: 'Low',
  medium: 'Med',
  high: 'High',
};

function formatDate(iso: string | null): string {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function isOverdue(iso: string | null): boolean {
  if (!iso) return false;
  return new Date(iso) < new Date();
}

export default function TaskCard({ task, onEdit, onDelete, onStatusChange }: Props) {
  return (
    <div className="task-card">
      <div className="task-card-header">
        <span className="task-title">{task.title}</span>
        <div className="task-card-actions">
          <button className="btn btn-ghost" onClick={onEdit}>Edit</button>
          <button className="btn btn-danger" onClick={onDelete}>Delete</button>
        </div>
      </div>

      {task.description && (
        <p className="task-description">{task.description}</p>
      )}

      <div className="task-meta">
        <span className={`badge badge-priority-${task.priority}`}>
          {PRIORITY_LABELS[task.priority]}
        </span>
        <select
          className="status-select"
          value={task.status}
          onChange={e => onStatusChange(e.target.value as Task['status'])}
        >
          {(Object.keys(STATUS_LABELS) as Task['status'][]).map(s => (
            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
          ))}
        </select>
        {task.tags.map(tag => (
          <span key={tag} className="tag">{tag}</span>
        ))}
      </div>

      <div className="task-footer">
        <span className="task-assignee">{task.assignee || '—'}</span>
        {task.dueDate && (
          <span className={`task-due${isOverdue(task.dueDate) && task.status !== 'done' ? ' overdue' : ''}`}>
            Due {formatDate(task.dueDate)}
          </span>
        )}
      </div>
    </div>
  );
}
