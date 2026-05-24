import type { ChatResponse, QueryRunDetail, QueryRunListItem, StreamEvent } from '../types/api';

export async function fetchHistory(): Promise<QueryRunListItem[]> {
  const response = await fetch('/history?limit=50');
  if (!response.ok) throw new Error(`history failed: ${response.status}`);
  const payload = await response.json();
  return payload.items ?? [];
}

export async function fetchRun(id: number): Promise<QueryRunDetail | null> {
  const response = await fetch(`/history/${id}`);
  if (!response.ok) throw new Error(`history item failed: ${response.status}`);
  const payload = await response.json();
  return payload.item ?? null;
}

export async function clearHistory(): Promise<void> {
  const response = await fetch('/history?delete_files=true', { method: 'DELETE' });
  if (!response.ok) throw new Error(`clear history failed: ${response.status}`);
}

export async function sendChat(query: string, signal?: AbortSignal): Promise<ChatResponse> {
  const response = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, page: '1', limit: '100', save: true }),
    signal
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.answer || payload.warnings?.join('\n') || `chat failed: ${response.status}`);
  return payload;
}

export async function streamChat(
  query: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal
): Promise<ChatResponse> {
  const response = await fetch('/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, page: '1', limit: '100', save: true }),
    signal
  });
  if (response.status === 404 || !response.body) return sendChat(query, signal);
  if (!response.ok) throw new Error(`stream failed: ${response.status}`);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() || '';

    for (const block of blocks) {
      const parsed = parseSseBlock(block);
      if (!parsed) continue;
      onEvent(parsed);
      if (parsed.event === 'done') return parsed.data as unknown as ChatResponse;
      if (parsed.event === 'error') throw new Error(String(parsed.data.message || parsed.data.answer || 'stream error'));
    }
  }

  throw new Error('stream ended before done');
}

function parseSseBlock(block: string): StreamEvent | null {
  let event = '';
  let data = '';
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7).trim();
    if (line.startsWith('data: ')) data += line.slice(6).trim();
  }
  if (!event || !data) return null;
  return { event, data: JSON.parse(data) };
}
