import { useState } from 'react';
import { Trash2, AlertTriangle, RotateCcw, Info } from 'lucide-react';
import { api } from '@/api';

export default function SettingsPage() {
  const [confirming, setConfirming] = useState(false);

  const handleForget = async () => {
    if (!confirming) { setConfirming(true); return; }
    await api.forgetAll();
    setConfirming(false);
    alert('所有数据已删除');
  };

  return (
    <div className="h-full overflow-y-auto p-6 max-w-2xl">
      <h2 className="text-xl font-display font-bold mb-6">设置</h2>

      <div className="space-y-5">
        <div className="glass-card p-5">
          <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2"><Info size={14} className="text-brand-400" /> 关于</h3>
          <p className="text-sm text-gray-400">心迹回声 (EmoEcho) v0.2.0</p>
          <p className="text-xs text-gray-500 mt-2">
            本地优先的桌面数字人格 Agent。融合依恋理论、NVC、CBT、MI
            四套心理学框架构建 EAF 情感管线算法。支持流式逐天人格提取与档案馆时序可视化。
          </p>
        </div>

        <div className="glass-card p-5">
          <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2"><RotateCcw size={14} /> 会话管理</h3>
          <button onClick={() => api.newSession()} className="btn-ghost text-xs">
            重置会话上下文
          </button>
        </div>

        <div className="glass-card p-5 border-red-900/20">
          <h3 className="text-sm font-semibold text-red-400 mb-3 flex items-center gap-2">
            <AlertTriangle size={14} /> 危险操作
          </h3>
          <p className="text-xs text-red-300/60 mb-3">
            一键遗忘将永久删除所有记忆、对话历史、反馈和自适应配置。此操作不可恢复。
          </p>
          <button
            onClick={handleForget}
            className={`rounded-full px-4 py-2 text-sm transition-all flex items-center gap-2 ${
              confirming
                ? 'bg-red-600 hover:bg-red-700 text-white shadow-lg shadow-red-600/20'
                : 'bg-red-900/30 hover:bg-red-900/50 text-red-300 border border-red-800/30'
            }`}
          >
            <Trash2 size={14} />
            {confirming ? '确认删除所有数据' : '一键遗忘'}
          </button>
        </div>
      </div>
    </div>
  );
}
