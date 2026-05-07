import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { ArrowLeft, CalendarDays, Tag, MessageSquare } from 'lucide-react';
import { api } from '@/api';

interface Snapshot {
  day: string;
  day_summary: string;
  new_tags?: string[];
  e3_estimate?: { empathy: number; stability: number; boundary: number };
  cumulative_tags?: string[];
  cumulative_e3?: { empathy: number; stability: number; boundary: number };
  message_count: number;
  target_msg_count: number;
}

export default function ArchivePage() {
  const { slug } = useParams<{ slug: string }>();
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [baseline, setBaseline] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    api.getDailySnapshots(slug)
      .then(r => {
        setSnapshots(r.snapshots as unknown as Snapshot[]);
        setBaseline(r.e3_baseline);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [slug]);

  const chartData = snapshots
    .filter(s => s.cumulative_e3)
    .map(s => ({
      day: s.day.slice(5),
      ...s.cumulative_e3,
    }));

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-gray-500 text-sm">加载档案馆...</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="flex items-center gap-3 mb-6">
        <Link to="/profile" className="text-gray-500 hover:text-gray-300 p-1">
          <ArrowLeft size={18} />
        </Link>
        <h2 className="text-xl font-bold">档案馆 — {slug}</h2>
        <span className="text-xs text-gray-500">{snapshots.length} 天记录</span>
      </div>

      {/* E3 时序图 */}
      {chartData.length > 1 && (
        <div className="glass-card p-5 mb-6">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">E3 性格演变时序图</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="day" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} domain={[0, 1]} />
              <Tooltip
                contentStyle={{
                  background: 'rgba(17, 24, 39, 0.95)',
                  border: '1px solid rgba(55, 65, 81, 0.6)',
                  borderRadius: '12px',
                  fontSize: 12,
                }}
              />
              <Line type="monotone" dataKey="empathy" stroke="#a855f7" strokeWidth={2} dot={false} name="共情度" />
              <Line type="monotone" dataKey="stability" stroke="#22c55e" strokeWidth={2} dot={false} name="稳定度" />
              <Line type="monotone" dataKey="boundary" stroke="#ef4444" strokeWidth={2} dot={false} name="边界感" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 基线信息 */}
      {baseline && Object.keys(baseline).length > 0 && (
        <div className="grid grid-cols-3 gap-3 mb-6">
          {[
            { key: 'empathy', label: '共情度', color: 'text-purple-400' },
            { key: 'stability', label: '稳定度', color: 'text-green-400' },
            { key: 'boundary', label: '边界感', color: 'text-red-400' },
          ].map(({ key, label, color }) => (
            <div key={key} className="glass-card p-3 text-center">
              <p className="text-xs text-gray-500">{label}基线</p>
              <p className={`text-2xl font-mono font-bold ${color}`}>
                {((baseline[key] || 0) * 100).toFixed(0)}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* 时间轴 */}
      <div className="relative">
        <div className="absolute left-4 top-0 bottom-0 w-px bg-gray-800" />
        <div className="space-y-4">
          {snapshots.map((snap, i) => (
            <div key={snap.day} className="relative pl-10">
              {/* 时间轴节点 */}
              <div className={`absolute left-2.5 w-3 h-3 rounded-full border-2 ${
                snap.e3_estimate ? 'border-brand-500 bg-brand-500/30' : 'border-gray-600 bg-gray-800'
              }`} style={{ top: '1.25rem' }} />

              <div className="glass-card p-4">
                <div className="flex items-center gap-2 mb-2">
                  <CalendarDays size={14} className="text-gray-500" />
                  <span className="text-sm font-semibold text-gray-300">{snap.day}</span>
                  <span className="text-xs text-gray-600 ml-auto flex items-center gap-1">
                    <MessageSquare size={10} /> {snap.message_count} 条
                  </span>
                </div>

                {snap.day_summary && (
                  <p className="text-xs text-gray-400 mb-2">{snap.day_summary}</p>
                )}

                {snap.new_tags && snap.new_tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-2">
                    {snap.new_tags.map((t, j) => (
                      <span key={j} className="flex items-center gap-0.5 bg-brand-600/20 text-brand-400 text-[10px] px-2 py-0.5 rounded-full">
                        <Tag size={8} />{t}
                      </span>
                    ))}
                  </div>
                )}

                {snap.e3_estimate && (
                  <div className="flex gap-4 text-[10px]">
                    <span className="text-purple-400">E: {((snap.e3_estimate.empathy || 0) * 100).toFixed(0)}%</span>
                    <span className="text-green-400">S: {((snap.e3_estimate.stability || 0) * 100).toFixed(0)}%</span>
                    <span className="text-red-400">B: {((snap.e3_estimate.boundary || 0) * 100).toFixed(0)}%</span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {snapshots.length === 0 && (
        <div className="text-center py-16 text-gray-600 text-sm">
          暂无日快照数据，请先通过人格页面进行流式分析
        </div>
      )}
    </div>
  );
}
