'use client';

import { useState, useEffect, useCallback } from 'react';
import type { Task, TaskFormData } from '@/types';
import TaskCard from '@/components/TaskCard';
import TaskForm from '@/components/TaskForm';

type Mode = 'idle' | 'create' | 'edit';

export default function Home() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [priorityFilter, setPriorityFilter] = useState('');
  const [mode, setMode] = useState<Mode>('idle');
  const [editingTask, setEditingTask] = useState<Task | null>(null);

  const fetchTasks = useCallback(async () => {
    const params = new URLSearchParams();
    if (statusFilter) params.set('status', statusFilter);
    if (priorityFilter) params.set('priority', priorityFilter);
    const res = await fetch(`/api/tasks?${params}`);
    setTasks(await res.json());
    setLoading(false);
  }, [statusFilter, priorityFilter]);

  useEffect(() => { fetchTasks(); }, [fetchTasks]);

  const handleCreate = async (data: TaskFormData) => {
    await fetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    setMode('idle');
    fetchTasks();
  };

  const handleUpdate = async (id: string, data: TaskFormData) => {
    await fetch(`/api/tasks/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    setMode('idle');
    setEditingTask(null);
    fetchTasks();
  };

  const handleDelete = async (id: string) => {
    await fetch(`/api/tasks/${id}`, { method: 'DELETE' });
    fetchTasks();
  };

  const handleStatusChange = async (id: string, status: Task['status']) => {
    await fetch(`/api/tasks/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    fetchTasks();
  };

  const openEdit = (task: Task) => {
    setEditingTask(task);
    setMode('edit');
  };

  const openCreate = () => {
    setEditingTask(null);
    setMode(m => m === 'create' ? 'idle' : 'create');
  };

  const cancel = () => { setMode('idle'); setEditingTask(null); };

  const counts = {
    todo: tasks.filter(t => t.status === 'todo').length,
    in_progress: tasks.filter(t => t.status === 'in_progress').length,
    done: tasks.filter(t => t.status === 'done').length,
  };

  return (
    <div className="container">
      <div className="page-header">
        <div>
          <div className="page-title">Task Board</div>
          <div className="page-subtitle">
            {counts.todo} todo · {counts.in_progress} in progress · {counts.done} done
          </div>
        </div>
        <button className="btn btn-primary" onClick={openCreate}>
          {mode === 'create' ? 'Cancel' : '+ New Task'}
        </button>
      </div>

      {mode === 'create' && (
        <TaskForm onSubmit={handleCreate} onCancel={cancel} />
      )}

      {mode === 'edit' && editingTask && (
        <TaskForm
          task={editingTask}
          onSubmit={data => handleUpdate(editingTask.id, data)}
          onCancel={cancel}
        />
      )}

      <div className="filters">
        <select
          className="filter-select"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
        >
          <option value="">All Statuses</option>
          <option value="todo">Todo</option>
          <option value="in_progress">In Progress</option>
          <option value="done">Done</option>
        </select>

        <select
          className="filter-select"
          value={priorityFilter}
          onChange={e => setPriorityFilter(e.target.value)}
        >
          <option value="">All Priorities</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>

        <span className="filter-count">{tasks.length} task{tasks.length !== 1 ? 's' : ''}</span>
      </div>

      {loading ? (
        <div className="loading">Loading…</div>
      ) : (
        <div className="task-grid">
          {tasks.map(task => (
            <TaskCard
              key={task.id}
              task={task}
              onEdit={() => openEdit(task)}
              onDelete={() => handleDelete(task.id)}
              onStatusChange={status => handleStatusChange(task.id, status)}
            />
          ))}
          {tasks.length === 0 && (
            <div className="empty-state">No tasks match the current filters.</div>
          )}
        </div>
      )}
    </div>
  );
}
