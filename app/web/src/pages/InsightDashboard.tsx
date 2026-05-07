import { useState, useEffect, useCallback } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, Radar,
  LineChart, Line, Legend,
  CartesianGrid,
} from 'recharts';
import { RefreshCw, Loader2 } from 'lucide-react';
import { api } from '@/api';

const REFRESH_INTERVAL = 15000;

function Card({ title, children, onRefresh }: { title: string; children: React.ReactNode; onRefresh?: () => void }) {
  return (
    <div className="glass-card p-5 relative group">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-300">{title}</h3>
        {onRefresh && (
          <button onClick={onRefresh} className="opacity-0 group-hover:opacity-100 text-gray-600 hover:text-brand-400 transition-all p-1 rounded-lg hover:bg-white/[0.04]" title="刷新">
            <RefreshCw size={13} />
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

const tooltipStyle = {
  contentStyle: {
    background: 'rgba(10, 14, 26, 0.95)',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    borderRadius: '12px',
    fontSize: 12,
    backdropFilter: 'blur(12px)',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
  },
  labelStyle: { color: '#9ca3af' },
};

function EmotionRiver() {
  const [data, setData] = useState<Record<string, unknown>[]>([]);
  const load = useCallback(() => { api.emotionTimeline(80).then(r => setData(r.data as Record<string, unknown>[])); }, []);
  useEffect(() => { load(); const t = setInterval(load, REFRESH_INTERVAL); return () => clearInterval(t); }, [load]);
  if (!data.length) return <p className="text-gray-600 text-xs text-center py-8">对话后这里将出现情绪河流</p>;
  const formatted = data.map((d, i) => ({ ...d, turn: `第${i + 1}轮` }));
  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={formatted}>
        <defs>
          <linearGradient id="gradSad" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#3b82f6" stopOpacity={0.5} /><stop offset="95%" stopColor="#3b82f6" stopOpacity={0.05} /></linearGradient>
          <linearGradient id="gradAnger" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#ef4444" stopOpacity={0.5} /><stop offset="95%" stopColor="#ef4444" stopOpacity={0.05} /></linearGradient>
          <linearGradient id="gradAnx" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#f97316" stopOpacity={0.5} /><stop offset="95%" stopColor="#f97316" stopOpacity={0.05} /></linearGradient>
          <linearGradient id="gradLone" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.5} /><stop offset="95%" stopColor="#8b5cf6" stopOpacity={0.05} /></linearGradient>
          <linearGradient id="gradWarm" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#f59e0b" stopOpacity={0.5} /><stop offset="95%" stopColor="#f59e0b" stopOpacity={0.05} /></linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
        <XAxis dataKey="turn" tick={{ fontSize: 10, fill: '#6b7280' }} />
        <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
        <Tooltip {...tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 11, color: '#9ca3af' }} />
        <Area type="monotone" dataKey="emotion_sadness" stackId="1" stroke="#3b82f6" fill="url(#gradSad)" name="悲伤" />
        <Area type="monotone" dataKey="emotion_anger" stackId="1" stroke="#ef4444" fill="url(#gradAnger)" name="愤怒" />
        <Area type="monotone" dataKey="emotion_anxiety" stackId="1" stroke="#f97316" fill="url(#gradAnx)" name="焦虑" />
        <Area type="monotone" dataKey="emotion_loneliness" stackId="1" stroke="#8b5cf6" fill="url(#gradLone)" name="孤独" />
        <Area type="monotone" dataKey="emotion_warmth" stackId="1" stroke="#f59e0b" fill="url(#gradWarm)" name="温暖" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function RelationshipRadar() {
  const [dims, setDims] = useState<{ name: string; value: number }[]>([]);
  const [baselineDims, setBaselineDims] = useState<{ name: string; value: number }[]>([]);
  const load = useCallback(() => { api.relationshipRadar().then(r => setDims(r.dimensions)); }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, REFRESH_INTERVAL);
    api.listPersonas().then(r => {
      if (r.personas.length > 0) {
        api.insightsBaseline(r.personas[0]).then(b => setBaselineDims(b.radar_baseline)).catch(() => {});
      }
    });
    return () => clearInterval(t);
  }, [load]);

  const hasDims = dims.length > 0;
  const hasBaseline = baselineDims.length > 0;
  if (!hasDims && !hasBaseline) return <p className="text-gray-600 text-xs text-center py-8">对话或创建人格后将出现关系雷达</p>;

  const source = hasDims ? dims : baselineDims;
  const formatted = source.map(d => {
    const bl = baselineDims.find(b => b.name === d.name);
    return { name: d.name, value: Math.round(d.value * 100), baseline: bl ? Math.round(bl.value * 100) : 0, fullMark: 100 };
  });

  return (
    <ResponsiveContainer width="100%" height={280}>
      <RadarChart data={formatted} cx="50%" cy="50%">
        <PolarGrid stroke="rgba(255,255,255,0.06)" gridType="circle" />
        <PolarAngleAxis dataKey="name" tick={{ fontSize: 12, fill: '#d1d5db', fontWeight: 500 }} />
        {hasBaseline && (
          <Radar dataKey="baseline" stroke="#6b7280" fill="#6b7280" fillOpacity={0.08} strokeWidth={1} strokeDasharray="4 4" name="基线" />
        )}
        <Radar dataKey="value" stroke="#a855f7" fill="#a855f7" fillOpacity={0.2} strokeWidth={2} dot={{ r: 4, fill: '#a855f7', strokeWidth: 0 }} name="当前" />
        <Tooltip {...tooltipStyle} formatter={(v: number) => [`${v}%`, '得分']} />
      </RadarChart>
    </ResponsiveContainer>
  );
}

function PersonalityDrift() {
  const [data, setData] = useState<Record<string, unknown>[]>([]);
  const load = useCallback(() => { api.personalityDrift().then(r => setData(r.data as Record<string, unknown>[])); }, []);
  useEffect(() => { load(); const t = setInterval(load, REFRESH_INTERVAL); return () => clearInterval(t); }, [load]);
  if (!data.length) return <p className="text-gray-600 text-xs text-center py-8">累计对话后将追踪性格漂移</p>;
  const formatted = data.map((d, i) => ({ ...d, window: `窗口${i + 1}` }));
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={formatted}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
        <XAxis dataKey="window" tick={{ fontSize: 10, fill: '#6b7280' }} />
        <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} domain={[0, 1]} />
        <Tooltip {...tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 11, color: '#9ca3af' }} />
        <Line type="monotone" dataKey="empathy" stroke="#a855f7" strokeWidth={2.5} dot={false} name="共情度" />
        <Line type="monotone" dataKey="stability" stroke="#22c55e" strokeWidth={2.5} dot={false} name="稳定度" />
        <Line type="monotone" dataKey="boundary" stroke="#ef4444" strokeWidth={2.5} dot={false} name="边界感" />
      </LineChart>
    </ResponsiveContainer>
  );
}

function E3Dashboard() {
  const [data, setData] = useState<Record<string, unknown>[]>([]);
  const [baseline, setBaseline] = useState<Record<string, number>>({});
  const load = useCallback(() => { api.e3History(60).then(r => setData(r.data as Record<string, unknown>[])); }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, REFRESH_INTERVAL);
    api.listPersonas().then(r => {
      if (r.personas.length > 0) {
        api.insightsBaseline(r.personas[0]).then(b => setBaseline(b.e3_baseline)).catch(() => {});
      }
    });
    return () => clearInterval(t);
  }, [load]);

  const hasData = data.length > 0;
  const hasBaseline = Object.keys(baseline).length > 0;
  if (!hasData && !hasBaseline) return <p className="text-gray-600 text-xs text-center py-8">对话或创建人格后将显示 E3 仪表盘</p>;

  const latest = hasData
    ? { empathy: Number(data[data.length - 1].e3_empathy), stability: Number(data[data.length - 1].e3_stability), boundary: Number(data[data.length - 1].e3_boundary) }
    : { empathy: baseline.empathy || 0.5, stability: baseline.stability || 0.5, boundary: baseline.boundary || 0.5 };

  const gaugeItems = [
    { label: '共情', key: 'empathy', value: latest.empathy, color: '#a855f7' },
    { label: '稳定', key: 'stability', value: latest.stability, color: '#22c55e' },
    { label: '边界', key: 'boundary', value: latest.boundary, color: '#ef4444' },
  ];

  return (
    <div>
      <div className="flex gap-6 mb-4 justify-center">
        {gaugeItems.map(g => (
          <div key={g.key} className="text-center">
            <div className="relative w-16 h-16 mx-auto">
              <svg viewBox="0 0 36 36" className="w-16 h-16 -rotate-90">
                <circle cx="18" cy="18" r="15.9155" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="3" />
                {hasBaseline && baseline[g.key] && (
                  <circle cx="18" cy="18" r="15.9155" fill="none" stroke={g.color} strokeWidth="3" strokeDasharray={`${(baseline[g.key] ?? 0) * 100} ${100 - (baseline[g.key] ?? 0) * 100}`} strokeLinecap="round" opacity={0.2} />
                )}
                <circle cx="18" cy="18" r="15.9155" fill="none" stroke={g.color} strokeWidth="3" strokeDasharray={`${g.value * 100} ${100 - g.value * 100}`} strokeLinecap="round" className="transition-all duration-700" />
              </svg>
              <span className="absolute inset-0 flex items-center justify-center text-xs font-bold font-mono" style={{ color: g.color }}>
                {(g.value * 100).toFixed(0)}
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-1">{g.label}</p>
            {hasBaseline && baseline[g.key] != null && (
              <p className="text-[10px] text-gray-600">基线 {((baseline[g.key] ?? 0) * 100).toFixed(0)}</p>
            )}
          </div>
        ))}
      </div>
      {hasData && (
        <ResponsiveContainer width="100%" height={150}>
          <LineChart data={data.map((d, i) => ({ ...d, turn: `${i + 1}` }))}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
            <XAxis dataKey="turn" tick={{ fontSize: 9, fill: '#6b7280' }} />
            <YAxis tick={{ fontSize: 9, fill: '#6b7280' }} domain={[0, 1]} />
            <Tooltip {...tooltipStyle} />
            <Line type="monotone" dataKey="e3_empathy" stroke="#a855f7" strokeWidth={1.5} dot={false} name="共情" />
            <Line type="monotone" dataKey="e3_stability" stroke="#22c55e" strokeWidth={1.5} dot={false} name="稳定" />
            <Line type="monotone" dataKey="e3_boundary" stroke="#ef4444" strokeWidth={1.5} dot={false} name="边界" />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function Heatmap() {
  const [data, setData] = useState<{ weekday: number; hour: number; count: number; avg_intensity: number }[]>([]);
  const load = useCallback(() => { api.heatmap().then(r => setData(r.data as typeof data)); }, []);
  useEffect(() => { load(); const t = setInterval(load, REFRESH_INTERVAL); return () => clearInterval(t); }, [load]);
  if (!data.length) return <p className="text-gray-600 text-xs text-center py-8">对话后这里将显示活跃热力图</p>;

  const days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
  const maxCount = Math.max(...data.map(d => d.count), 1);

  return (
    <div className="overflow-x-auto">
      <div className="grid gap-[2px]" style={{ gridTemplateColumns: `48px repeat(24, 1fr)` }}>
        <div />
        {Array.from({ length: 24 }, (_, i) => (
          <div key={i} className="text-center text-[10px] text-gray-600 pb-1">{`${i}时`}</div>
        ))}
        {days.map((day, di) => (
          <>
            <div key={`label-${di}`} className="text-[11px] text-gray-500 flex items-center font-medium">{day}</div>
            {Array.from({ length: 24 }, (_, hi) => {
              const cell = data.find(d => d.weekday === di && d.hour === hi);
              const opacity = cell ? cell.count / maxCount : 0;
              return (
                <div
                  key={`${di}-${hi}`}
                  className="aspect-square rounded-sm transition-colors"
                  style={{ background: `rgba(168, 85, 247, ${Math.max(opacity * 0.85, 0.03)})` }}
                  title={cell ? `${cell.count} 条对话，平均情绪强度 ${(cell.avg_intensity * 100).toFixed(0)}%` : '无数据'}
                />
              );
            })}
          </>
        ))}
      </div>
    </div>
  );
}

export default function InsightDashboard() {
  const [, setTick] = useState(0);
  const forceRefresh = () => setTick(t => t + 1);

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-display font-bold">关系洞察</h2>
        <button onClick={forceRefresh} className="flex items-center gap-1.5 text-xs btn-ghost py-1.5 px-3">
          <RefreshCw size={12} /> 刷新全部
        </button>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card title="情绪时间河流"><EmotionRiver /></Card>
        <Card title="关系维度雷达"><RelationshipRadar /></Card>
        <Card title="性格漂移轨迹"><PersonalityDrift /></Card>
        <Card title="E3 情感评分仪表盘"><E3Dashboard /></Card>
        <div className="lg:col-span-2">
          <Card title="对话活跃热力图"><Heatmap /></Card>
        </div>
      </div>
    </div>
  );
}
