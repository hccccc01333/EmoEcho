import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, UserCircle, Tag, FileText, X, ChevronRight, Loader2, CheckCircle2, Trash2, RefreshCw, Archive } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { api, type PreviewResult, type DetectResult } from '@/api';

const ACCEPT = '.txt,.csv,.json,.md,.log,.docx';

type Step = 'upload' | 'detect' | 'select_user' | 'preview' | 'streaming' | 'done';

interface StreamProgress {
  day: string;
  progress: number;
  total: number;
  summary?: string;
  tags?: string[];
}

export default function ProfilePage() {
  const navigate = useNavigate();
  const [slugs, setSlugs] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);

  const [step, setStep] = useState<Step>('upload');
  const [newSlug, setNewSlug] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [detectData, setDetectData] = useState<DetectResult | null>(null);
  const [myUsername, setMyUsername] = useState('');
  const [previewData, setPreviewData] = useState<PreviewResult | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // SSE streaming state
  const [streamProgress, setStreamProgress] = useState<StreamProgress[]>([]);
  const [streamDone, setStreamDone] = useState(false);

  useEffect(() => { api.listPersonas().then(r => setSlugs(r.personas)); }, []);
  useEffect(() => {
    if (selected) api.getPersona(selected).then(setProfile);
    else setProfile(null);
  }, [selected]);

  const addFiles = useCallback((incoming: FileList | File[]) => {
    const arr = Array.from(incoming);
    setFiles(prev => { const names = new Set(prev.map(f => f.name)); return [...prev, ...arr.filter(f => !names.has(f.name))]; });
  }, []);
  const removeFile = (name: string) => setFiles(prev => prev.filter(f => f.name !== name));
  const handleDrop = useCallback((e: React.DragEvent) => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files); }, [addFiles]);

  const resetFlow = () => { setStep('upload'); setNewSlug(''); setFiles([]); setMyUsername(''); setDetectData(null); setPreviewData(null); setError(''); setLoading(false); setStreamProgress([]); setStreamDone(false); };

  const doDetect = async () => {
    if (!newSlug.trim() || files.length === 0) return;
    setLoading(true); setError(''); setStep('detect');
    try {
      const result = await api.detectSpeakers(files);
      setDetectData(result);
      setStep('select_user');
    } catch (e: unknown) { setError(e instanceof Error ? e.message : '格式检测失败'); setStep('upload'); }
    finally { setLoading(false); }
  };

  const doPreview = async (selectedUsername: string) => {
    setMyUsername(selectedUsername); setLoading(true); setError('');
    try {
      const result = await api.previewChat(selectedUsername, { cacheKey: detectData?.cache_key });
      setPreviewData(result); setStep('preview');
    } catch (e: unknown) { setError(e instanceof Error ? e.message : '预检失败'); setStep('select_user'); }
    finally { setLoading(false); }
  };

  // SSE streaming analysis
  const doStreamAnalyze = async () => {
    if (!previewData) return;
    setStep('streaming'); setError(''); setStreamProgress([]); setStreamDone(false);
    try {
      await api.streamExtractSSE(
        newSlug.trim(), myUsername.trim(),
        { cacheKey: previewData.cache_key },
        (evt) => {
          if (evt.event === 'day_done') {
            const d = evt.data as Record<string, unknown>;
            setStreamProgress(prev => [...prev, {
              day: d.day as string,
              progress: d.progress as number,
              total: d.total as number,
              summary: (d.snapshot as Record<string, unknown>)?.day_summary as string,
              tags: (d.snapshot as Record<string, unknown>)?.new_tags as string[],
            }]);
          } else if (evt.event === 'day_skipped') {
            const d = evt.data as Record<string, unknown>;
            setStreamProgress(prev => [...prev, { day: d.day as string, progress: d.progress as number, total: d.total as number, summary: '跳过' }]);
          } else if (evt.event === 'complete') {
            const d = evt.data as Record<string, unknown>;
            setProfile(d.profile as Record<string, unknown>);
            setSlugs(prev => [...new Set([...prev, newSlug.trim()])]);
            setSelected(newSlug.trim());
            setStreamDone(true);
            setStep('done');
          }
        }
      );
    } catch (e: unknown) { setError(e instanceof Error ? e.message : '分析失败'); setStep('preview'); }
  };

  const handleDelete = async (slug: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`确定删除「${slug}」吗？`)) return;
    await api.deletePersona(slug);
    setSlugs(prev => prev.filter(s => s !== slug));
    if (selected === slug) { setSelected(null); setProfile(null); }
  };

  const toneStyle = (profile?.tone_style ?? {}) as Record<string, unknown>;
  const emotionPatterns = (profile?.emotion_patterns ?? {}) as Record<string, unknown>;
  const relMemory = (profile?.relationship_memory ?? {}) as Record<string, unknown>;
  const tags = (profile?.personality_tags ?? []) as string[];
  const boundaries = (profile?.boundary_rules ?? []) as string[];
  const e3Base = (profile?.e3_baseline ?? {}) as Record<string, number>;

  return (
    <div className="h-full overflow-y-auto p-6">
      <h2 className="text-xl font-display font-bold mb-6">人格档案</h2>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: persona list + create flow */}
        <div className="space-y-4">
          <div className="glass-card p-4">
            <h3 className="text-sm font-semibold text-gray-300 mb-3">已有人格</h3>
            {slugs.length === 0 && <p className="text-gray-600 text-xs">暂无人格档案</p>}
            <div className="space-y-1">
              {slugs.map(s => (
                <div key={s} className={`group flex items-center px-3 py-2 rounded-xl text-sm transition-all cursor-pointer ${selected === s ? 'bg-white/[0.10] text-white' : 'hover:bg-white/[0.04] text-gray-400'}`} onClick={() => setSelected(s)}>
                  <UserCircle size={14} className="mr-2 shrink-0" />
                  <span className="flex-1 truncate">{s}</span>
                  <div className="hidden group-hover:flex items-center gap-1 shrink-0">
                    <button onClick={() => navigate(`/archive/${s}`)} className="text-gray-600 hover:text-accent-cyan p-0.5" title="档案馆"><Archive size={12} /></button>
                    <button onClick={() => { resetFlow(); setNewSlug(s); }} className="text-gray-600 hover:text-brand-400 p-0.5" title="重新生成"><RefreshCw size={12} /></button>
                    <button onClick={e => handleDelete(s, e)} className="text-gray-600 hover:text-red-400 p-0.5" title="删除"><Trash2 size={12} /></button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="glass-card p-4">
            {error && <div className="bg-red-950/40 border border-red-900/40 rounded-lg px-3 py-2 text-xs text-red-300 mb-3">{error}</div>}

            {step === 'upload' && (
              <>
                <h3 className="text-sm font-semibold text-gray-300 mb-3"><Upload size={14} className="inline mr-1" />上传聊天记录</h3>
                <input value={newSlug} onChange={e => setNewSlug(e.target.value)} placeholder="人格代号 (如: 初恋)" className="w-full bg-white/[0.06] rounded-xl px-3 py-2 text-sm mb-2 outline-none focus:ring-1 focus:ring-brand-500/50 placeholder-gray-500 border border-white/[0.08]" />
                <div onDragOver={e => { e.preventDefault(); setDragOver(true); }} onDragLeave={() => setDragOver(false)} onDrop={handleDrop} onClick={() => fileRef.current?.click()} className={`w-full border-2 border-dashed rounded-xl px-4 py-6 mb-2 flex flex-col items-center justify-center cursor-pointer transition-colors ${dragOver ? 'border-brand-400 bg-brand-600/10' : 'border-white/[0.08] hover:border-white/[0.15] bg-white/[0.02]'}`}>
                  <Upload size={24} className={`mb-2 ${dragOver ? 'text-brand-400' : 'text-gray-500'}`} />
                  <p className="text-xs text-gray-400">拖拽文件或 <span className="text-brand-400 underline">点击选择</span></p>
                  <p className="text-xs text-gray-600 mt-1">支持 .txt .csv .json .md .log .docx</p>
                  <input ref={fileRef} type="file" accept={ACCEPT} multiple className="hidden" onChange={e => { if (e.target.files?.length) addFiles(e.target.files); e.target.value = ''; }} />
                </div>
                {files.length > 0 && (
                  <div className="space-y-1.5 mb-2 max-h-32 overflow-y-auto">{files.map(f => (
                    <div key={f.name} className="flex items-center gap-2 bg-white/[0.04] rounded-lg px-3 py-1.5 text-xs">
                      <FileText size={12} className="text-brand-400 shrink-0" />
                      <span className="text-gray-300 truncate flex-1">{f.name}</span>
                      <span className="text-gray-600 shrink-0">{(f.size / 1024).toFixed(0)} KB</span>
                      <button onClick={e => { e.stopPropagation(); removeFile(f.name); }} className="text-gray-500 hover:text-red-400"><X size={12} /></button>
                    </div>
                  ))}</div>
                )}
                <button onClick={doDetect} disabled={!newSlug.trim() || files.length === 0} className="w-full btn-primary disabled:opacity-40">下一步 <ChevronRight size={14} className="inline" /></button>
              </>
            )}

            {step === 'detect' && (<div className="flex flex-col items-center py-8"><Loader2 size={28} className="text-brand-400 animate-spin mb-3" /><p className="text-sm text-gray-300">正在检测聊天格式...</p></div>)}

            {step === 'select_user' && detectData && (
              <>
                <h3 className="text-sm font-semibold text-gray-300 mb-2">你是哪个？</h3>
                <p className="text-xs text-gray-500 mb-3">选择你自己，其余的就是对方</p>
                <div className="space-y-2 mb-3">{detectData.speakers.map(s => (
                  <button key={s} onClick={() => doPreview(s)} disabled={loading} className="w-full flex items-center gap-3 glass-card-hover px-4 py-3 text-sm text-left">
                    <UserCircle size={20} className="text-gray-500 shrink-0" /><span className="text-gray-200 flex-1">{s}</span><span className="text-xs text-gray-600">选择</span>
                  </button>
                ))}</div>
                {loading && <div className="flex items-center justify-center gap-2 text-xs text-gray-500"><Loader2 size={14} className="animate-spin" /> 解析中...</div>}
                <button onClick={() => setStep('upload')} className="w-full btn-ghost mt-2">返回</button>
              </>
            )}

            {step === 'preview' && previewData && (
              <>
                <h3 className="text-sm font-semibold text-gray-300 mb-3">解析结果确认</h3>
                <div className="space-y-2 text-xs mb-3">
                  <div className="glass-card p-3">
                    <p className="text-gray-400 mb-1">发言者</p>
                    <div className="flex gap-2 flex-wrap">{previewData.stats.speakers.map(s => (
                      <span key={s} className={`px-2 py-0.5 rounded-full text-xs ${s === previewData.stats.my_username ? 'bg-accent-cyan/20 text-cyan-300 border border-cyan-800/40' : 'bg-brand-600/20 text-brand-400 border border-brand-600/30'}`}>
                        {s === previewData.stats.my_username ? `${s} (你)` : `${s} (对方)`}
                      </span>
                    ))}</div>
                  </div>
                  <div className="grid grid-cols-3 gap-2">{[
                    { label: '总消息', value: previewData.stats.total_messages, color: 'text-brand-400' },
                    { label: '你的', value: previewData.stats.my_count, color: 'text-cyan-400' },
                    { label: '对方的', value: previewData.stats.target_count, color: 'text-brand-400' },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="glass-card p-2 text-center"><p className="text-gray-500">{label}</p><p className={`${color} font-mono text-lg`}>{value}</p></div>
                  ))}</div>
                  <div className="glass-card p-3">
                    <p className="text-gray-300">共 <span className="text-brand-400 font-semibold">{previewData.preview.total_days}</span> 天，<span className="text-brand-400 font-semibold">{previewData.preview.active_days}</span> 天高活跃，<span className="text-brand-400 font-semibold">{previewData.preview.chunk_count}</span> 个对话块</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setStep('select_user')} className="flex-1 btn-ghost">返回</button>
                  <button onClick={doStreamAnalyze} className="flex-1 btn-primary">开始流式分析</button>
                </div>
              </>
            )}

            {step === 'streaming' && (
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-gray-300">流式分析中...</h3>
                <p className="text-[10px] text-gray-600">逐天发送给 DeepSeek，可以切到对话页先聊天</p>
                <div className="max-h-48 overflow-y-auto space-y-1.5">
                  <AnimatePresence>{streamProgress.map((sp, i) => (
                    <motion.div key={sp.day} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} className="flex items-center gap-2 text-xs">
                      <CheckCircle2 size={12} className="text-green-400 shrink-0" />
                      <span className="text-gray-400 w-20 shrink-0">{sp.day}</span>
                      <span className="text-gray-500 truncate flex-1">{sp.summary || ''}</span>
                      <span className="text-gray-600 shrink-0">{sp.progress}/{sp.total}</span>
                    </motion.div>
                  ))}</AnimatePresence>
                </div>
                {streamProgress.length > 0 && (
                  <div className="w-full bg-white/[0.06] rounded-full h-1.5">
                    <div className="bg-gradient-to-r from-brand-500 to-accent-violet h-1.5 rounded-full transition-all" style={{ width: `${(streamProgress[streamProgress.length - 1].progress / streamProgress[streamProgress.length - 1].total) * 100}%` }} />
                  </div>
                )}
              </div>
            )}

            {step === 'done' && (
              <div className="flex flex-col items-center py-6">
                <CheckCircle2 size={32} className="text-green-400 mb-3" />
                <p className="text-sm text-green-300 mb-1">人格档案生成完成</p>
                <p className="text-xs text-gray-500 mb-3">已分析 {streamProgress.length} 天对话</p>
                <div className="flex gap-2">
                  <button onClick={() => navigate(`/archive/${newSlug.trim()}`)} className="btn-ghost text-xs">查看档案馆</button>
                  <button onClick={resetFlow} className="btn-primary text-xs">创建新的</button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right: profile display */}
        <div className="lg:col-span-2">
          {!profile ? (
            <div className="glass-card p-8 flex items-center justify-center h-64">
              <p className="text-gray-600 text-sm">选择或创建一个人格档案</p>
            </div>
          ) : (
            <div className="space-y-4 animate-fade-in">
              <div className="glass-card p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-lg font-display font-semibold text-brand-400 mb-1">{String(profile.nickname || selected)}</h3>
                    <p className="text-sm text-gray-400">{String(profile.core_identity || '')}</p>
                  </div>
                  {selected && (
                    <div className="flex gap-1.5">
                      <button onClick={() => navigate(`/archive/${selected}`)} className="text-gray-600 hover:text-accent-cyan p-1.5 rounded-lg hover:bg-white/[0.04]" title="档案馆"><Archive size={14} /></button>
                      <button onClick={() => { resetFlow(); setNewSlug(selected); }} className="text-gray-600 hover:text-brand-400 p-1.5 rounded-lg hover:bg-white/[0.04]" title="重建"><RefreshCw size={14} /></button>
                      <button onClick={e => handleDelete(selected, e)} className="text-gray-600 hover:text-red-400 p-1.5 rounded-lg hover:bg-white/[0.04]" title="删除"><Trash2 size={14} /></button>
                    </div>
                  )}
                </div>
                <div className="flex flex-wrap gap-2 mt-3">{tags.map((t, i) => (
                  <span key={i} className="bg-brand-600/20 text-brand-400 text-xs px-2.5 py-1 rounded-full"><Tag size={10} className="inline mr-1" />{t}</span>
                ))}</div>
              </div>

              {/* E3 Baseline */}
              {Object.keys(e3Base).length > 0 && (
                <div className="grid grid-cols-3 gap-3">
                  {[{ key: 'empathy', label: '共情度', color: 'text-purple-400' }, { key: 'stability', label: '稳定度', color: 'text-green-400' }, { key: 'boundary', label: '边界感', color: 'text-red-400' }].map(({ key, label, color }) => (
                    <div key={key} className="glass-card p-3 text-center">
                      <p className="text-[10px] text-gray-500">{label}基线</p>
                      <p className={`text-xl font-mono font-bold ${color}`}>{((e3Base[key] || 0) * 100).toFixed(0)}</p>
                    </div>
                  ))}
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div className="glass-card p-4"><h4 className="text-xs font-semibold text-gray-400 mb-2">依恋类型</h4><p className="text-sm text-brand-400">{String(profile.attachment_style || '')}</p></div>
                <div className="glass-card p-4"><h4 className="text-xs font-semibold text-gray-400 mb-2">爱的语言</h4><p className="text-sm text-brand-400">{String(profile.love_language || '')}</p></div>
              </div>

              <div className="glass-card p-4">
                <h4 className="text-xs font-semibold text-gray-400 mb-2">语气风格</h4>
                <div className="text-sm text-gray-300 space-y-1">
                  <p>口头禅: {(toneStyle.vocabulary as string[] || []).join('、') || '无'}</p>
                  <p>句式: {String(toneStyle.sentence_pattern || '自然')}</p>
                  <p>表达长度: {String(toneStyle.verbosity || '适中')}</p>
                </div>
              </div>

              <div className="glass-card p-4">
                <h4 className="text-xs font-semibold text-gray-400 mb-2">情感模式</h4>
                <div className="text-sm text-gray-300 space-y-1">
                  <p>安抚方式: {String(emotionPatterns.comfort_strategy || '')}</p>
                  <p>生气模式: {String(emotionPatterns.anger_pattern || '')}</p>
                  <p>脆弱信号: {String(emotionPatterns.vulnerability_signal || '')}</p>
                </div>
              </div>

              <div className="glass-card p-4">
                <h4 className="text-xs font-semibold text-gray-400 mb-2">关系记忆</h4>
                <div className="text-sm text-gray-300 space-y-1">{(relMemory.key_events as string[] || []).map((evt, i) => (<p key={i} className="text-xs">- {evt}</p>))}</div>
              </div>

              {boundaries.length > 0 && (
                <div className="glass-card p-4 border-red-900/20">
                  <h4 className="text-xs font-semibold text-red-400 mb-2">边界规则</h4>
                  {boundaries.map((r, i) => (<p key={i} className="text-xs text-red-300">- {r}</p>))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
