const BASE = '';

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export interface ChatMessage {
  reply: string;
  e3_score: { empathy: number; stability: number; boundary: number; policy: string };
  eaf: Record<string, unknown>;
  policy: string;
  strategy: string;
  skill_used: string | null;
  safety_level: string;
  memories_used: number;
  latency_ms: number;
  msg_id: string;
}

export interface DetectResult {
  cache_key: string;
  format_source: string;
  speakers: string[];
}

export interface PreviewResult {
  cache_key: string;
  format_source: string;
  stats: {
    total_messages: number;
    speakers: string[];
    my_username: string;
    target_name: string;
    my_count: number;
    target_count: number;
  };
  preview: {
    daily_stats: { day: string; total: number; my_count: number; target_count: number; is_low_activity: boolean }[];
    chunk_count: number;
    chunks_preview: { date_start: string; date_end: string; total_count: number; day_count: number }[];
    total_messages: number;
    total_days: number;
    active_days: number;
  };
}

export interface UploadResult {
  slug: string;
  path: string;
  profile: Record<string, unknown>;
  stats: Record<string, unknown>;
}

export interface Conversation {
  id: string;
  title: string;
  message_count: number;
  persona_slug: string | null;
  updated_at: number;
}

export interface ConversationDetail {
  id: string;
  title: string;
  messages: { role: string; content: string; meta?: ChatMessage }[];
  persona_slug: string | null;
  created_at: number;
  updated_at: number;
  archived: boolean;
}

export const api = {
  // ── Chat ──
  chat: (message: string, persona_slug?: string) =>
    request<ChatMessage>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, persona_slug }),
    }),

  newSession: () => request('/chat/new-session', { method: 'POST' }),

  // ── Chat History ──
  listConversations: (archived = false) =>
    request<{ conversations: Conversation[] }>(`/chat/history?archived=${archived}`),

  saveConversation: (title: string, messages: object[], persona_slug?: string) =>
    request<{ id: string; title: string }>('/chat/history', {
      method: 'POST',
      body: JSON.stringify({ title, messages, persona_slug }),
    }),

  loadConversation: (id: string) =>
    request<ConversationDetail>(`/chat/history/${id}`),

  updateConversation: (id: string, messages: object[], title?: string) =>
    request(`/chat/history/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ messages, title }),
    }),

  deleteConversation: (id: string) =>
    request(`/chat/history/${id}`, { method: 'DELETE' }),

  archiveConversation: (id: string) =>
    request<{ archived: boolean }>(`/chat/history/${id}/archive`, { method: 'PATCH' }),

  // ── Persona ──
  detectSpeakers: async (files: File[]): Promise<DetectResult> => {
    const fd = new FormData();
    files.forEach(f => fd.append('files', f));
    const res = await fetch('/persona/detect-speakers', { method: 'POST', body: fd });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
  },

  previewChat: async (myUsername: string, opts: { files?: File[]; cacheKey?: string }): Promise<PreviewResult> => {
    const fd = new FormData();
    fd.append('my_username', myUsername);
    if (opts.cacheKey) fd.append('cache_key', opts.cacheKey);
    if (opts.files) opts.files.forEach(f => fd.append('files', f));
    const res = await fetch('/persona/preview', { method: 'POST', body: fd });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
  },

  uploadPersona: async (slug: string, myUsername: string, opts: { files?: File[]; cacheKey?: string }): Promise<UploadResult> => {
    const fd = new FormData();
    fd.append('slug', slug);
    fd.append('my_username', myUsername);
    if (opts.cacheKey) fd.append('cache_key', opts.cacheKey);
    if (opts.files) opts.files.forEach(f => fd.append('files', f));
    const res = await fetch('/persona/upload', { method: 'POST', body: fd });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json();
  },

  createPersona: (slug: string, material: string) =>
    request('/persona/create', {
      method: 'POST',
      body: JSON.stringify({ slug, material }),
    }),

  getPersona: (slug: string) => request<Record<string, unknown>>(`/persona/${slug}`),

  listPersonas: () => request<{ personas: string[] }>('/persona/list/all'),

  deletePersona: (slug: string) =>
    request<{ status: string }>(`/persona/${slug}`, { method: 'DELETE' }),

  streamExtract: (slug: string, myUsername: string, opts: { files?: File[]; cacheKey?: string }): EventSource | null => {
    return null; // SSE handled via custom fetch, see streamExtractSSE
  },

  streamExtractSSE: async (
    slug: string, myUsername: string,
    opts: { cacheKey?: string },
    onEvent: (evt: { event: string; data: Record<string, unknown> }) => void,
  ) => {
    const fd = new FormData();
    fd.append('slug', slug);
    fd.append('my_username', myUsername);
    if (opts.cacheKey) fd.append('cache_key', opts.cacheKey);
    const res = await fetch('/persona/stream-extract', { method: 'POST', body: fd });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    const reader = res.body?.getReader();
    if (!reader) throw new Error('No response body');
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';
      for (const part of parts) {
        const lines = part.split('\n');
        let event = 'message';
        let data = '{}';
        for (const line of lines) {
          if (line.startsWith('event: ')) event = line.slice(7).trim();
          if (line.startsWith('data: ')) data = line.slice(6);
        }
        try { onEvent({ event, data: JSON.parse(data) }); } catch { /* skip */ }
      }
    }
  },

  getDailySnapshots: (slug: string) =>
    request<{ snapshots: Record<string, unknown>[]; e3_baseline: Record<string, number> }>(
      `/persona/${slug}/daily-snapshots`
    ),

  insightsBaseline: (slug: string) =>
    request<{
      e3_baseline: Record<string, number>;
      radar_baseline: { name: string; value: number }[];
      daily_snapshots: Record<string, unknown>[];
    }>(`/insights/baseline/${slug}`),

  // ── Memory ──
  searchMemory: (q: string) => request<{ results: unknown[] }>(`/memory/search?q=${encodeURIComponent(q)}`),

  forgetAll: () => request('/memory/forget', { method: 'POST' }),

  // ── Insights ──
  emotionTimeline: (limit = 100) => request<{ data: unknown[] }>(`/insights/emotion-timeline?limit=${limit}`),

  e3History: (limit = 100) => request<{ data: unknown[] }>(`/insights/e3-history?limit=${limit}`),

  sessionSummary: () => request<Record<string, unknown>>('/insights/session-summary'),

  heatmap: () => request<{ data: unknown[] }>('/insights/heatmap'),

  relationshipRadar: () =>
    request<{ dimensions: { name: string; value: number }[] }>('/insights/relationship-radar'),

  personalityDrift: () =>
    request<{ data: unknown[]; corrections: unknown[] }>('/insights/personality-drift'),
};
