'use client';

import { useState } from 'react';
import type { Task, TaskFormData } from '@/types';

interface Props {
  task?: Task;
  onSubmit: (data: TaskFormData) => void;
  onCancel: () => void;
}

export default function TaskForm({ task, onSubmit, onCancel }: Props) {
  const [form, setForm] = useState<TaskFormData>({
    title: task?.title ?? '',
    description: task?.description ?? '',
    status: task?.status ?? 'todo',
    priority: task?.priority ?? 'medium',
    assignee: task?.assignee ?? '',
    tags: task?.tags ?? [],
    dueDate: task?.dueDate ?? null,
  });

  const [tagsInput, setTagsInput] = useState(task?.tags.join(', ') ?? '');

  function set<K extends keyof TaskFormData>(key: K, value: TaskFormData[K]) {
    setForm(f => ({ ...f, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const tags = tagsInput
      .split(',')
      .map(t => t.trim())
      .filter(Boolean);
    onSubmit({ ...form, tags });
  }

  return (
    <form className="task-form" onSubmit={handleSubmit}>
      <div className="form-title">{task ? 'Edit Task' : 'New Task'}</div>
      <div className="form-grid">
        <div className="form-field full">
          <label className="form-label">Title</label>
          <input
            className="form-input"
            required
            value={form.title}
            onChange={e => set('title', e.target.value)}
            placeholder="Task title"
          />
        </div>

        <div className="form-field full">
          <label className="form-label">Description</label>
          <textarea
            className="form-textarea"
            value={form.description}
            onChange={e => set('description', e.target.value)}
            placeholder="What needs to be done?"
          />
        </div>

        <div className="form-field">
          <label className="form-label">Status</label>
          <select
            className="form-select"
            value={form.status}
            onChange={e => set('status', e.target.value as Task['status'])}
          >
            <option value="todo">Todo</option>
            <option value="in_progress">In Progress</option>
            <option value="done">Done</option>
          </select>
        </div>

        <div className="form-field">
          <label className="form-label">Priority</label>
          <select
            className="form-select"
            value={form.priority}
            onChange={e => set('priority', e.target.value as Task['priority'])}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>

        <div className="form-field">
          <label className="form-label">Assignee</label>
          <input
            className="form-input"
            value={form.assignee}
            onChange={e => set('assignee', e.target.value)}
            placeholder="Name"
          />
        </div>

        <div className="form-field">
          <label className="form-label">Due Date</label>
          <input
            className="form-input"
            type="date"
            value={form.dueDate ? form.dueDate.slice(0, 10) : ''}
            onChange={e => set('dueDate', e.target.value ? `${e.target.value}T00:00:00Z` : null)}
          />
        </div>

        <div className="form-field full">
          <label className="form-label">Tags (comma-separated)</label>
          <input
            className="form-input"
            value={tagsInput}
            onChange={e => setTagsInput(e.target.value)}
            placeholder="backend, api, security"
          />
        </div>
      </div>

      <div className="form-actions">
        <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn-primary">
          {task ? 'Save Changes' : 'Create Task'}
        </button>
      </div>
    </form>
  );
}
