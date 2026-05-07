import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, ChevronDown, ChevronUp, Sparkles, Plus, Trash2, Archive, MessageSquare, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';
import { api, ChatMessage, type Conversation } from '@/api';

interface Msg {
  role: 'user' | 'assistant';
  content: string;
  meta?: ChatMessage;
}

function E3Ring({ e3 }: { e3: { empathy: number; stability: number; boundary: number } }) {
  const r = 28;
  const c = 2 * Math.PI * r;
  const segments = [
    { value: e3.empathy, color: '#a855f7', label: 'E' },
    { value: e3.stability, color: '#22c55e', label: 'S' },
    { value: e3.boundary, color: '#ef4444', label: 'B' },
  ];
  return (
    <div className="flex items-center gap-3">
      <svg width="72" height="72" viewBox="0 0 72 72">
        {segments.map((seg, i) => {
          const offset = c * (1 - seg.value);
          const rotation = i * 120 - 90;
          return (
            <circle
              key={seg.label}
              cx="36" cy="36" r={r}
              fill="none"
              stroke={seg.color}
              strokeWidth="4"
              strokeDasharray={`${c}`}
              strokeDashoffset={offset}
              strokeLinecap="round"
              opacity={0.8}
              transform={`rotate(${rotation} 36 36)`}
            />
          );
        })}
        <text x="36" y="40" textAnchor="middle" fill="white" fontSize="11" fontWeight="bold">E3</text>
      </svg>
      <div className="text-xs space-y-1">
        {segments.map(s => (
          <div key={s.label} className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: s.color }} />
            <span className="text-gray-400">{s.label}</span>
            <span className="text-gray-200 font-mono">{(s.value * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AgentThinking({ meta }: { meta: ChatMessage }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1.5">
      <button onClick={() => setOpen(!open)} className="text-xs text-gray-600 hover:text-gray-400 flex items-center gap-1 transition-colors">
        <Sparkles size={12} />
        Agent 思考过程
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-2 p-3 glass-card text-xs space-y-1 text-gray-400">
              <p>策略: <span className="text-brand-400">{meta.strategy}</span></p>
              <p>Policy: {meta.policy} | Safety: {meta.safety_level}</p>
              {meta.skill_used && <p>Skill: {meta.skill_used}</p>}
              <p>记忆命中: {meta.memories_used} 条 | 延迟: {meta.latency_ms.toFixed(0)}ms</p>
              {meta.eaf && (
                <>
                  <p>情绪阶段: {String((meta.eaf as Record<string,unknown>).emotion_stage || '')}</p>
                  <p>认知扭曲: {String((meta.eaf as Record<string,unknown>).distortion_type || 'none')} ({(Number((meta.eaf as Record<string,unknown>).distortion_score) * 100).toFixed(0)}%)</p>
                  <p>依恋激活: {(Number((meta.eaf as Record<string,unknown>).attachment_activation) * 100).toFixed(0)}% | 距离建议: {String((meta.eaf as Record<string,unknown>).distance_suggestion || '')}</p>
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}

export default function ChatPage() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [latestE3, setLatestE3] = useState<ChatMessage['e3_score'] | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [convList, setConvList] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const loadConvList = useCallback(async () => {
    try { const r = await api.listConversations(); setConvList(r.conversations); } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadConvList(); }, [loadConvList]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs]);

  const newChat = () => { autoSave(); setMsgs([]); setActiveConvId(null); setLatestE3(null); api.newSession(); };

  const autoSave = async () => {
    if (msgs.length === 0) return;
    try {
      if (activeConvId) {
        await api.updateConversation(activeConvId, msgs);
      } else {
        const title = msgs.find(m => m.role === 'user')?.content.slice(0, 30) || '新对话';
        const r = await api.saveConversation(title, msgs);
        setActiveConvId(r.id);
      }
      loadConvList();
    } catch { /* ignore */ }
  };

  const loadConv = async (id: string) => {
    autoSave();
    try {
      const data = await api.loadConversation(id);
      setMsgs(data.messages as Msg[]);
      setActiveConvId(id);
      const lastAssistant = [...data.messages].reverse().find(m => m.meta?.e3_score);
      if (lastAssistant?.meta?.e3_score) setLatestE3(lastAssistant.meta.e3_score);
    } catch { /* ignore */ }
  };

  const deleteConv = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await api.deleteConversation(id);
    if (activeConvId === id) { setMsgs([]); setActiveConvId(null); }
    loadConvList();
  };

  const archiveConv = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await api.archiveConversation(id);
    loadConvList();
  };

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    setMsgs(prev => [...prev, { role: 'user', content: text }]);
    setLoading(true);
    try {
      const res = await api.chat(text);
      setLatestE3(res.e3_score);
      setMsgs(prev => [...prev, { role: 'assistant', content: res.reply, meta: res }]);
    } catch (e) {
      setMsgs(prev => [...prev, { role: 'assistant', content: `[Error] ${e}` }]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const timer = setTimeout(() => { if (msgs.length > 0) autoSave(); }, 5000);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [msgs.length]);

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 260, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="border-r border-white/[0.06] bg-black/20 backdrop-blur-xl flex flex-col shrink-0 overflow-hidden"
          >
            <div className="p-3 border-b border-white/[0.06]">
              <button onClick={newChat} className="w-full flex items-center justify-center gap-2 btn-primary text-xs py-2">
                <Plus size={14} /> 新对话
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {convList.length === 0 && <p className="text-gray-600 text-xs text-center mt-8">暂无对话记录</p>}
              {convList.map(conv => (
                <div
                  key={conv.id}
                  onClick={() => loadConv(conv.id)}
                  className={clsx(
                    'group flex items-center gap-2 px-3 py-2.5 rounded-xl cursor-pointer transition-all text-sm',
                    activeConvId === conv.id ? 'bg-white/[0.10] text-white' : 'text-gray-500 hover:bg-white/[0.04] hover:text-gray-300'
                  )}
                >
                  <MessageSquare size={14} className="shrink-0 opacity-50" />
                  <div className="flex-1 min-w-0">
                    <p className="truncate text-xs">{conv.title}</p>
                    <p className="text-[10px] text-gray-600">{timeAgo(conv.updated_at)}</p>
                  </div>
                  <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
                    <button onClick={e => archiveConv(conv.id, e)} className="text-gray-600 hover:text-yellow-400 p-0.5"><Archive size={11} /></button>
                    <button onClick={e => deleteConv(conv.id, e)} className="text-gray-600 hover:text-red-400 p-0.5"><Trash2 size={11} /></button>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main chat area */}
      <div className="flex-1 flex flex-col">
        <header className="px-6 py-3 border-b border-white/[0.06] flex items-center justify-between backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <button onClick={() => setSidebarOpen(!sidebarOpen)} className="text-gray-600 hover:text-gray-300 p-1.5 rounded-lg hover:bg-white/[0.04] transition-colors">
              {sidebarOpen ? <PanelLeftClose size={16} /> : <PanelLeftOpen size={16} />}
            </button>
            <h1 className="text-base font-display font-semibold text-gray-200">心迹回声</h1>
          </div>
          {latestE3 && <E3Ring e3={latestE3} />}
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {msgs.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-gray-600 gap-2">
              <p className="text-sm">输入一条消息开始对话</p>
              <p className="text-xs text-gray-700">可在人格页面上传聊天记录生成对方的数字人格</p>
            </div>
          )}
          {msgs.map((m, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={clsx('max-w-[70%]', m.role === 'user' ? 'ml-auto' : 'mr-auto')}
            >
              <div
                className={clsx(
                  'px-4 py-2.5 rounded-2xl text-sm leading-relaxed',
                  m.role === 'user'
                    ? 'bg-gradient-to-r from-brand-600 to-accent-violet text-white rounded-br-md shadow-lg shadow-brand-600/10'
                    : 'glass-card text-gray-200 rounded-bl-md',
                )}
              >
                {m.content}
              </div>
              {m.meta && <AgentThinking meta={m.meta} />}
            </motion.div>
          ))}
          {loading && (
            <div className="mr-auto">
              <div className="glass-card px-4 py-2.5 rounded-2xl rounded-bl-md text-sm text-gray-400">
                <span className="inline-flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 bg-brand-400 rounded-full animate-pulse" />
                  <span className="w-1.5 h-1.5 bg-brand-400 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }} />
                  <span className="w-1.5 h-1.5 bg-brand-400 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }} />
                </span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="px-6 py-4 border-t border-white/[0.06]">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
              placeholder="说点什么..."
              className="flex-1 bg-white/[0.06] rounded-2xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-brand-500/30 placeholder-gray-600 border border-white/[0.08] transition-shadow"
            />
            <button
              onClick={send}
              disabled={loading || !input.trim()}
              className="btn-primary rounded-2xl px-4 py-2.5 disabled:opacity-30"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
