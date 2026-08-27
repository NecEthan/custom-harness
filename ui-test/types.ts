export interface Task {
  id: string;
  title: string;
  description: string;
  status: 'todo' | 'in_progress' | 'done';
  priority: 'low' | 'medium' | 'high';
  assignee: string;
  tags: string[];
  createdAt: string;
  dueDate: string | null;
}

export type TaskFormData = Omit<Task, 'id' | 'createdAt'>;
