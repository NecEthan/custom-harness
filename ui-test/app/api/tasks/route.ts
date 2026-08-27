import { NextResponse } from 'next/server';
import fs from 'fs/promises';
import path from 'path';
import type { Task } from '@/types';

const DATA_FILE = path.join(process.cwd(), 'data', 'tasks.json');

async function readTasks(): Promise<Task[]> {
  const raw = await fs.readFile(DATA_FILE, 'utf-8');
  return (JSON.parse(raw) as { tasks: Task[] }).tasks;
}

async function writeTasks(tasks: Task[]): Promise<void> {
  await fs.writeFile(DATA_FILE, JSON.stringify({ tasks }, null, 2));
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const status = searchParams.get('status');
  const priority = searchParams.get('priority');

  let tasks = await readTasks();
  if (status) tasks = tasks.filter(t => t.status === status);
  if (priority) tasks = tasks.filter(t => t.priority === priority);

  return NextResponse.json(tasks);
}

export async function POST(request: Request) {
  const body = await request.json() as Partial<Task>;
  const tasks = await readTasks();

  const newTask: Task = {
    id: `task-${Date.now()}`,
    title: body.title ?? 'Untitled',
    description: body.description ?? '',
    status: body.status ?? 'todo',
    priority: body.priority ?? 'medium',
    assignee: body.assignee ?? '',
    tags: body.tags ?? [],
    createdAt: new Date().toISOString(),
    dueDate: body.dueDate ?? null,
  };

  tasks.push(newTask);
  await writeTasks(tasks);
  return NextResponse.json(newTask, { status: 201 });
}
