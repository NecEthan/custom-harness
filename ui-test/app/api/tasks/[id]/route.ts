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

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const tasks = await readTasks();
  const task = tasks.find(t => t.id === id);
  if (!task) return NextResponse.json({ error: 'Not found' }, { status: 404 });
  return NextResponse.json(task);
}

export async function PUT(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await request.json() as Partial<Task>;
  const tasks = await readTasks();
  const idx = tasks.findIndex(t => t.id === id);
  if (idx === -1) return NextResponse.json({ error: 'Not found' }, { status: 404 });
  tasks[idx] = { ...tasks[idx], ...body, id };
  await writeTasks(tasks);
  return NextResponse.json(tasks[idx]);
}

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const tasks = await readTasks();
  const filtered = tasks.filter(t => t.id !== id);
  if (filtered.length === tasks.length) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 });
  }
  await writeTasks(filtered);
  return new NextResponse(null, { status: 204 });
}
